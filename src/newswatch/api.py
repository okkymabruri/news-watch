"""
Synchronous Python API for newswatch.

This module provides synchronous wrapper functions around the async newswatch functionality,
making it easy to use newswatch in scripts and interactive environments.

author: Okky Mabruri <okkymbrur@gmail.com>
maintainer: Okky Mabruri <okkymbrur@gmail.com>
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

import pandas as pd

from .exceptions import NewsWatchError, ValidationError
from .main import get_available_scrapers


class MockArgs:
    """Mock argparse.Namespace for passing parameters to async main function."""

    def __init__(
        self,
        keywords: str,
        start_date: str,
        scrapers: str = "auto",
        output_format: str = "xlsx",
        verbose: bool = False,
    ):
        self.keywords = keywords
        self.start_date = start_date
        self.scrapers = scrapers
        self.output_format = output_format
        self.verbose = verbose


async def _collect_queue_results(
    queue: asyncio.Queue, scrapers_done_event: asyncio.Event
) -> List[Dict]:
    """
    Collect all items from the async queue into a list with improved coordination.

    Uses adaptive timeout strategy:
    - While scrapers running: longer timeout to allow for slow scrapers
    - After scrapers done: shorter timeout to collect remaining items quickly
    """
    results = []
    items_collected = 0

    while True:
        try:
            # adaptive timeout based on scraper status
            if scrapers_done_event.is_set():
                # scrapers finished, short timeout for remaining items
                timeout = 5
            else:
                # scrapers still running, longer timeout
                timeout = 60

            item = await asyncio.wait_for(queue.get(), timeout=timeout)

        except asyncio.TimeoutError:
            if scrapers_done_event.is_set():
                # scrapers done and timeout reached - normal completion
                logging.debug(
                    f"Collection completed after scrapers finished. Collected {items_collected} items."
                )
                break
            else:
                # scrapers still running but no items - continue waiting
                logging.debug(
                    f"Waiting for scrapers to complete... Collected {items_collected} items so far."
                )
                continue

        except (RuntimeError, asyncio.CancelledError) as e:
            if isinstance(e, asyncio.CancelledError) or "Event loop is closed" in str(
                e
            ):
                logging.debug(
                    f"Collector cancelled. Collected {items_collected} items."
                )
                break
            else:
                raise

        if item is None:  # sentinel value to stop
            logging.debug(
                f"Received sentinel. Collection completed with {items_collected} items."
            )
            break

        # format datetime objects as strings for json serialization
        if isinstance(item.get("publish_date"), datetime):
            item["publish_date"] = item["publish_date"].strftime("%Y-%m-%d %H:%M:%S")

        results.append(item)
        items_collected += 1

    logging.debug(f"Final collection result: {items_collected} items collected")
    return results


async def _async_scrape_to_list(
    keywords: str,
    start_date: str,
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
) -> List[Dict]:
    """
    Internal async function to scrape and return results as list.

    Uses producer-consumer pattern with async queue:
    1. Creates collector task that runs concurrently with scrapers
    2. Scrapers put articles into queue (producers)
    3. Collector reads from queue and collects into list (consumer)
    4. Sentinel value (None) signals end of scraping
    5. Proper task cancellation and timeout handling
    """
    if not verbose:
        logging.disable(logging.CRITICAL)

    # validate inputs
    try:
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(
            f"Invalid date format: {start_date}. Use YYYY-MM-DD format."
        )

    if not keywords.strip():
        raise ValidationError("Keywords cannot be empty.")

    # get available scrapers and validate selection
    scraper_classes, linux_excluded_scrapers = get_available_scrapers()
    if scrapers not in ["auto", "all"] and scrapers:
        import platform

        scraper_list = [name.strip().lower() for name in scrapers.split(",")]

        allowed_scrapers = dict(scraper_classes)
        if platform.system().lower() == "linux":
            # Allow explicit selection of Linux-excluded scrapers.
            allowed_scrapers.update(linux_excluded_scrapers)

        invalid_scrapers = [s for s in scraper_list if s not in allowed_scrapers]
        if invalid_scrapers:
            raise ValidationError(
                f"Invalid scrapers: {invalid_scrapers}. Available: {list(allowed_scrapers.keys())}"
            )

    # create queue for collecting results and event for coordination
    queue = asyncio.Queue()
    scrapers_done_event = asyncio.Event()

    # start collector task (runs concurrently with scrapers)
    collector_task = asyncio.create_task(
        _collect_queue_results(queue, scrapers_done_event)
    )

    # determine which scrapers to run
    force_all_scrapers = scrapers.lower() == "all"

    if force_all_scrapers:
        import platform

        if platform.system().lower() == "linux":
            scraper_classes.update(linux_excluded_scrapers)
            logging.warning(
                f"Forcing all scrapers on Linux - may cause errors: {', '.join(linux_excluded_scrapers.keys())}"
            )

    if scrapers.lower() in ["all", "auto"]:
        scrapers_to_run = list(scraper_classes.keys())
    else:
        scrapers_to_run = [name.strip().lower() for name in scrapers.split(",")]

    # If the caller explicitly requested Linux-excluded scrapers, enable them.
    import platform

    if platform.system().lower() == "linux":
        requested_excluded = [
            s
            for s in scrapers_to_run
            if s in linux_excluded_scrapers and s not in scraper_classes
        ]
        if requested_excluded:
            scraper_classes.update(
                {name: linux_excluded_scrapers[name] for name in requested_excluded}
            )
            logging.warning(
                "Using Linux-excluded scrapers (may fail due to WAF/Cloudflare/anti-bot): %s",
                ", ".join(requested_excluded),
            )

    # instantiate scrapers
    scraper_instances = []
    for scraper_name in scrapers_to_run:
        scraper_info = scraper_classes.get(scraper_name)
        if scraper_info:
            scraper_class = scraper_info["class"]
            scraper_params = scraper_info["params"]
            scraper_instance = scraper_class(
                keywords, start_date=start_date_obj, queue_=queue, **scraper_params
            )
            scraper_instances.append(scraper_instance)
        else:
            logging.warning(f"scraper '{scraper_name}' is not recognized.")

    if not scraper_instances:
        logging.error("no valid scrapers selected.")
        scrapers_done_event.set()  # signal completion even with no scrapers
        collector_task.cancel()
        try:
            await collector_task
        except asyncio.CancelledError:
            pass
        return []

    # track scraper statistics for debugging
    total_scrapers = len(scraper_instances)
    logging.debug(
        f"Starting {total_scrapers} scrapers: {[type(s).__name__ for s in scraper_instances]}"
    )

    # run all scrapers concurrently with timeout
    scraper_tasks = []
    try:
        scraper_tasks = [
            asyncio.create_task(scraper.scrape()) for scraper in scraper_instances
        ]
        # respect caller-provided timeout for overall scrape
        await asyncio.wait_for(asyncio.gather(*scraper_tasks), timeout=timeout)
        logging.debug(f"All {total_scrapers} scrapers completed successfully")
    except asyncio.TimeoutError:
        logging.warning(
            f"Scraping took too long and was stopped after {timeout} seconds. {total_scrapers} scrapers were running."
        )
    except Exception as e:
        logging.error(f"Error during scraping: {e}")
    finally:
        # cancel any remaining scraper tasks
        cancelled_count = 0
        for task in scraper_tasks:
            if not task.done():
                task.cancel()
                cancelled_count += 1

        if cancelled_count > 0:
            logging.debug(f"Cancelled {cancelled_count} unfinished scraper tasks")

        # wait for cancelled tasks to complete
        if scraper_tasks:
            try:
                await asyncio.gather(*scraper_tasks, return_exceptions=True)
            except Exception:
                pass

        # important: signal that all scrapers are done BEFORE sending sentinel
        scrapers_done_event.set()
        logging.debug("Scrapers completion event set")

        # now send sentinel to stop collector
        await queue.put(None)
        logging.debug("Sentinel sent to collector")

    # wait for collector to finish (no timeout needed since we coordinate via event)
    try:
        results = await collector_task
        logging.debug(f"Collector completed successfully with {len(results)} items")
        return results
    except asyncio.CancelledError:
        logging.debug("Collector was cancelled")
        return []
    except Exception as e:
        logging.error(f"Error in collector task: {e}")
        return []


def scrape(
    keywords: str,
    start_date: str,
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    **kwargs,
) -> List[Dict]:
    """
    Scrape news articles and return as list of dictionaries.

    Args:
        keywords (str): Comma-separated keywords to search for
        start_date (str): Start date in YYYY-MM-DD format
        scrapers (str): Scrapers to use - "auto", "all", or comma-separated list
        verbose (bool): Enable verbose logging
        timeout (int): Maximum time in seconds for scraping operation
        **kwargs: Additional parameters (for future compatibility)

    Returns:
        List[Dict]: List of article dictionaries with keys:
            - title: Article title
            - publish_date: Publication date as string
            - author: Article author
            - content: Article content
            - keyword: Matched keyword
            - category: Article category
            - source: News source
            - link: Article URL

    Raises:
        ValidationError: For invalid input parameters
        NewsWatchError: For other newswatch-related errors
    """
    try:
        return asyncio.run(
            _async_scrape_to_list(keywords, start_date, scrapers, verbose, timeout)
        )
    except KeyboardInterrupt:
        logging.info("Scraping interrupted by user")
        return []
    except (ValidationError, NewsWatchError):
        # re-raise our custom exceptions without wrapping
        raise
    except Exception as e:
        raise NewsWatchError(f"Error during scraping: {e}") from e


def scrape_to_dataframe(
    keywords: str,
    start_date: str,
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    **kwargs,
) -> pd.DataFrame:
    """
    Scrape news articles and return as pandas DataFrame.

    Args:
        keywords (str): Comma-separated keywords to search for
        start_date (str): Start date in YYYY-MM-DD format
        scrapers (str): Scrapers to use - "auto", "all", or comma-separated list
        verbose (bool): Enable verbose logging
        timeout (int): Maximum time in seconds for scraping operation
        **kwargs: Additional parameters (for future compatibility)

    Returns:
        pd.DataFrame: DataFrame with columns matching article dictionary keys

    Raises:
        ValidationError: For invalid input parameters
        NewsWatchError: For other newswatch-related errors
    """
    try:
        results = scrape(keywords, start_date, scrapers, verbose, timeout, **kwargs)

        # define column order
        columns = [
            "title",
            "publish_date",
            "author",
            "content",
            "keyword",
            "category",
            "source",
            "link",
        ]

        if not results:
            # return empty dataframe with proper columns
            return pd.DataFrame(columns=columns)

        df = pd.DataFrame(results, columns=columns)

        # convert publish_date back to datetime
        if "publish_date" in df.columns:
            df["publish_date"] = pd.to_datetime(df["publish_date"], errors="coerce")

        return df

    except Exception as e:
        if isinstance(e, (ValidationError, NewsWatchError)):
            raise
        raise NewsWatchError(f"Error creating DataFrame: {e}") from e


def scrape_to_file(
    keywords: str,
    start_date: str,
    output_path: Union[str, Path],
    output_format: str = "xlsx",
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    **kwargs,
) -> None:
    """
    Scrape news articles and save to file.

    Args:
        keywords (str): Comma-separated keywords to search for
        start_date (str): Start date in YYYY-MM-DD format
        output_path (Union[str, Path]): Path to save the output file
        output_format (str): Output format - "xlsx", "csv", or "json"
        scrapers (str): Scrapers to use - "auto", "all", or comma-separated list
        verbose (bool): Enable verbose logging
        timeout (int): Maximum time in seconds for scraping operation
        **kwargs: Additional parameters (for future compatibility)

    Raises:
        ValidationError: For invalid input parameters
        NewsWatchError: For other newswatch-related errors
    """
    # validate output format
    if output_format.lower() not in ["csv", "xlsx", "json"]:
        raise ValidationError(
            f"Invalid output format: {output_format}. Use 'csv', 'xlsx', or 'json'."
        )

    # ensure output path has correct extension
    output_path = Path(output_path)
    if not output_path.suffix:
        output_path = output_path.with_suffix(f".{output_format.lower()}")
    elif output_path.suffix.lower() != f".{output_format.lower()}":
        logging.warning(
            f"Output path extension {output_path.suffix} doesn't match format {output_format}"
        )

    try:
        # get results as dataframe
        df = scrape_to_dataframe(
            keywords, start_date, scrapers, verbose, timeout, **kwargs
        )

        if df.empty:
            logging.warning("No articles found. Creating empty file.")

        # save to file
        if output_format.lower() == "xlsx":
            df.to_excel(output_path, index=False)
        elif output_format.lower() == "json":
            # ensure dates are formatted as strings for JSON
            if "publish_date" in df.columns:
                df["publish_date"] = df["publish_date"].dt.strftime("%Y-%m-%d %H:%M:%S")
            # convert dataframe to json with proper formatting
            df.to_json(output_path, orient="records", indent=2, force_ascii=False)
        else:
            df.to_csv(output_path, index=False, encoding="utf-8")

        print(f"Data written to {output_path}")

    except Exception as e:
        if isinstance(e, (ValidationError, NewsWatchError)):
            raise
        raise NewsWatchError(f"Error saving to file: {e}") from e


def list_scrapers() -> List[str]:
    """
    Get list of available scrapers.

    Returns:
        List[str]: List of available scraper names
    """
    scraper_classes, _ = get_available_scrapers()
    return list(scraper_classes.keys())


# convenience functions for common use cases
def quick_scrape(
    keywords: str, days_back: int = 1, scrapers: str = "auto"
) -> pd.DataFrame:
    """
    Quick scrape for recent articles.

    Args:
        keywords (str): Keywords to search for
        days_back (int): Number of days back from today
        scrapers (str): Scrapers to use

    Returns:
        pd.DataFrame: Articles from the specified time period
    """
    from datetime import datetime, timedelta

    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    return scrape_to_dataframe(keywords, start_date, scrapers)
