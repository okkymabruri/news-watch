"""
Synchronous Python API for newswatch.

This module provides synchronous wrapper functions around the async newswatch functionality,
making it easy to use newswatch in scripts and interactive environments.

author: Okky Mabruri <okkymbrur@gmail.com>
maintainer: Okky Mabruri <okkymbrur@gmail.com>
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

import pandas as pd

from .exceptions import NewsWatchError, ValidationError
from .main import get_available_scrapers
from .main import _load_dedup_links, _parse_time_range


class MockArgs:
    """Mock argparse.Namespace for passing parameters to async main function."""

    def __init__(
        self,
        keywords: str | None,
        start_date: str | None,
        scrapers: str = "auto",
        output_format: str = "xlsx",
        verbose: bool = False,
        method: str = "search",
        limit: int | None = None,
        max_pages: int | None = None,
        time_range: str | None = None,
        dedup_file: str | None = None,
    ):
        self.keywords = keywords
        self.start_date = start_date
        self.scrapers = scrapers
        self.output_format = output_format
        self.verbose = verbose
        self.method = method
        self.limit = limit
        self.max_pages = max_pages
        self.time_range = time_range
        self.dedup_file = dedup_file


async def _collect_queue_results(
    queue: asyncio.Queue, scrapers_done_event: asyncio.Event, limit: int | None = None,
    limit_reached_event: asyncio.Event | None = None,
    dedup_links: set | None = None,
    time_range: tuple | None = None,
) -> List[Dict]:
    """
    Collect all items from the async queue into a list with improved coordination.

    Uses adaptive timeout strategy:
    - While scrapers running: longer timeout to allow for slow scrapers
    - After scrapers done: shorter timeout to collect remaining items quickly
    - Stops early if limit is reached and signals limit_reached_event
    """
    results = []
    items_collected = 0

    # Parse time range if provided
    time_start, time_end = (None, None)
    if time_range:
        time_start, time_end = time_range

    while True:
        # Check if we've reached the limit
        if limit is not None and items_collected >= limit:
            logging.debug(f"Reached limit of {limit} articles. Stopping collection.")
            if limit_reached_event:
                limit_reached_event.set()
            break

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

        # Skip duplicates
        if dedup_links is not None and item.get("link", "") in dedup_links:
            continue

        # Apply time range filter
        if time_start is not None or time_end is not None:
            pub_date = item.get("publish_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.fromisoformat(pub_date)
                    except ValueError:
                        continue
                if not isinstance(pub_date, datetime):
                    continue
                if time_start is not None and pub_date < time_start:
                    continue
                if time_end is not None and pub_date > time_end:
                    continue

        # format datetime objects as strings for json serialization
        if isinstance(item.get("publish_date"), datetime):
            item["publish_date"] = item["publish_date"].strftime("%Y-%m-%d %H:%M:%S")

        results.append(item)
        items_collected += 1

    logging.debug(f"Final collection result: {items_collected} items collected")
    return results


async def _async_scrape_to_list(
    keywords: str | None,
    start_date: str | None,
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    method: str = "search",
    limit: int | None = None,
    max_pages: int | None = None,
    *,
    scraper_timeout: int | None = None,
    time_range: str | None = None,
    dedup_file: str | None = None,
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
    if method not in {"search", "latest"}:
        raise ValidationError(
            f"Invalid method: {method}. Use 'search' or 'latest'."
        )

    if method == "search":
        if not start_date:
            raise ValidationError("Start date is required for search method.")
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise ValidationError(
                f"Invalid date format: {start_date}. Use YYYY-MM-DD format."
            )

        if not keywords or not keywords.strip():
            raise ValidationError("Keywords cannot be empty.")
    else:
        start_date_obj = None

    # get available scrapers and validate selection
    scraper_classes, _linux_excluded = get_available_scrapers(method=method)
    if scrapers not in ["auto", "all"] and scrapers:
        allowed_scrapers = dict(scraper_classes)
        scraper_list = [name.strip().lower() for name in scrapers.split(",")]

        invalid_scrapers = [s for s in scraper_list if s not in allowed_scrapers]
        if invalid_scrapers:
            raise ValidationError(
                f"Invalid scrapers: {invalid_scrapers}. Available: {list(allowed_scrapers.keys())}"
            )

    # Process dedup and time range parameters
    dedup_links = None
    if dedup_file:
        try:
            dedup_links = _load_dedup_links(dedup_file)
        except Exception as e:
            raise ValidationError(f"Failed to load dedup file: {e}") from e

    parsed_tr = None
    if time_range:
        try:
            parsed_tr = _parse_time_range(time_range)
        except Exception as e:
            raise ValidationError(f"Failed to parse time range: {e}") from e

    # create queue for collecting results and events for coordination
    queue = asyncio.Queue()
    scrapers_done_event = asyncio.Event()
    limit_reached_event = asyncio.Event()

    if scrapers.lower() in ["all", "auto"]:
        scrapers_to_run = list(scraper_classes.keys())
    else:
        scrapers_to_run = [name.strip().lower() for name in scrapers.split(",")]

    # instantiate scrapers
    scraper_instances = []
    for scraper_name in scrapers_to_run:
        scraper_info = scraper_classes.get(scraper_name)
        if scraper_info:
            scraper_class = scraper_info["class"]
            scraper_params = scraper_info["params"]
            scraper_instance = scraper_class(
                keywords or "latest",
                start_date=start_date_obj,
                queue_=queue,
                **scraper_params,
            )
            # Apply max_pages limit for latest mode
            if max_pages is not None:
                scraper_instance.max_latest_pages = max_pages
            # Wire dedup and time window to scraper for pre-fetch filtering
            if dedup_links is not None:
                scraper_instance.dedup_links = dedup_links
            if parsed_tr is not None:
                scraper_instance.start_datetime = parsed_tr[0]
                scraper_instance.end_datetime = parsed_tr[1]
            scraper_instances.append(scraper_instance)
        else:
            logging.warning(f"scraper '{scraper_name}' is not recognized.")

    if not scraper_instances:
        logging.error("no valid scrapers selected.")
        scrapers_done_event.set()
        parsed_tr = None
        if time_range:
            parsed_tr = _parse_time_range(time_range)
        collector_task = asyncio.create_task(
            _collect_queue_results(queue, scrapers_done_event, limit=limit,
                                   limit_reached_event=limit_reached_event,
                                   dedup_links=dedup_links, time_range=parsed_tr)
        )
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

    # run all scrapers concurrently with per-scraper timeout isolation
    scraper_stats: Dict[str, Dict] = {}

    async def _run_with_timeout(scraper, timeout_val):
        scraper_name = type(scraper).__name__
        try:
            if timeout_val:
                await asyncio.wait_for(scraper.scrape(method=method), timeout=timeout_val)
            else:
                await scraper.scrape(method=method)
            scraper_stats[scraper_name] = {"status": "ok"}
        except asyncio.TimeoutError:
            logging.warning(
                f"Scraper {scraper_name} timed out after {timeout_val}s"
            )
            scraper_stats[scraper_name] = {"status": "timeout"}
        except Exception as e:
            logging.error(f"Scraper {scraper_name} failed: {e}")
            scraper_stats[scraper_name] = {"status": "error"}

    scraper_tasks = [
        asyncio.create_task(_run_with_timeout(scraper, scraper_timeout))
        for scraper in scraper_instances
    ]

    # start collector task (runs concurrently with scrapers)
    # collector signals limit_reached_event instead of cancelling tasks
    collector_task = asyncio.create_task(
        _collect_queue_results(queue, scrapers_done_event, limit=limit,
                               limit_reached_event=limit_reached_event,
                               dedup_links=dedup_links, time_range=parsed_tr)
    )

    # race scraper completion against limit being reached
    try:
        all_scrapers_done = asyncio.gather(*scraper_tasks)
        limit_hit = asyncio.create_task(limit_reached_event.wait())

        done, pending = await asyncio.wait(
            [all_scrapers_done, limit_hit], timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not done:
            all_scrapers_done.cancel()
            for t in scraper_tasks:
                if not t.done():
                    t.cancel()
            logging.warning(
                f"Scraping took too long and was stopped after {timeout} seconds. {total_scrapers} scrapers were running."
            )
        elif limit_hit in done:
            # Limit reached — cancel remaining scraper work
            all_scrapers_done.cancel()
            for t in scraper_tasks:
                if not t.done():
                    t.cancel()
            # Allow cancelled tasks to resolve without propagating CancelledError
            for t in scraper_tasks:
                if not t.done():
                    try:
                        await t
                    except BaseException:
                        pass
            logging.debug("Limit reached, cancelled remaining scrapers")
        else:
            # Scrapers finished — clean up limit watcher
            limit_hit.cancel()
    except asyncio.TimeoutError:
        logging.warning(
            f"Scraping took too long and was stopped after {timeout} seconds. {total_scrapers} scrapers were running."
        )
        for t in scraper_tasks:
            if not t.done():
                t.cancel()
    except Exception as e:
        logging.error(f"Error during scraping: {e}")
        for t in scraper_tasks:
            if not t.done():
                t.cancel()
    finally:
        # Wait for any remaining tasks to resolve cleanly
        if scraper_tasks:
            await asyncio.gather(*scraper_tasks, return_exceptions=True)

        # signal that all scrapers are done BEFORE sending sentinel
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
    keywords: str | None = None,
    start_date: str | None = None,
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    method: str = "search",
    limit: int | None = None,
    max_pages: int | None = None,
    *,
    scraper_timeout: int | None = None,
    time_range: str | None = None,
    dedup_file: str | None = None,
    **kwargs,
) -> List[Dict]:
    """
    Scrape news articles and return as list of dictionaries.

    Args:
        keywords (str | None): Comma-separated keywords to search for
        start_date (str | None): Start date in YYYY-MM-DD format
        scrapers (str): Scrapers to use - "auto", "all", or comma-separated list
        verbose (bool): Enable verbose logging
        timeout (int): Maximum time in seconds for scraping operation
        method (str): Retrieval method - "search" or "latest"
        limit (int | None): Maximum number of articles to collect (latest mode)
        max_pages (int | None): Maximum pages to fetch per scraper (latest mode)
        time_range (str | None): Filter articles by time range. Format: ISO8601/ISO8601.
        dedup_file (str | None): Path to previous output file for deduplication.
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
            _async_scrape_to_list(
                keywords, start_date, scrapers, verbose, timeout, method, limit, max_pages,
                scraper_timeout=scraper_timeout,
                time_range=time_range, dedup_file=dedup_file,
            )
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
    keywords: str | None = None,
    start_date: str | None = None,
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    method: str = "search",
    limit: int | None = None,
    max_pages: int | None = None,
    *,
    scraper_timeout: int | None = None,
    time_range: str | None = None,
    dedup_file: str | None = None,
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
        method (str): Retrieval method - "search" or "latest"
        limit (int | None): Maximum number of articles to collect (latest mode)
        max_pages (int | None): Maximum pages to fetch per scraper (latest mode)
        time_range (str | None): Filter articles by time range. Format: ISO8601/ISO8601.
        dedup_file (str | None): Path to previous output file for deduplication.
        **kwargs: Additional parameters (for future compatibility)

    Returns:
        pd.DataFrame: DataFrame with columns matching article dictionary keys

    Raises:
        ValidationError: For invalid input parameters
        NewsWatchError: For other newswatch-related errors
    """
    try:
        results = scrape(
            keywords, start_date, scrapers, verbose, timeout, method, limit, max_pages,
            scraper_timeout=scraper_timeout, time_range=time_range, dedup_file=dedup_file, **kwargs
        )

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
    keywords: str | None,
    start_date: str | None,
    output_path: Union[str, Path],
    output_format: str = "xlsx",
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    method: str = "search",
    limit: int | None = None,
    max_pages: int | None = None,
    *,
    scraper_timeout: int | None = None,
    time_range: str | None = None,
    dedup_file: str | None = None,
    **kwargs,
) -> None:
    """
    Scrape news articles and save to file.

    Args:
        keywords (str): Comma-separated keywords to search for
        start_date (str): Start date in YYYY-MM-DD format
        output_path (Union[str, Path]): Path to save the output file
        output_format (str): Output format - "xlsx", "csv", "json", or "jsonl"
        scrapers (str): Scrapers to use - "auto", "all", or comma-separated list
        verbose (bool): Enable verbose logging
        timeout (int): Maximum time in seconds for scraping operation
        method (str): Retrieval method - "search" or "latest"
        limit (int | None): Maximum number of articles to collect (latest mode)
        max_pages (int | None): Maximum pages to fetch per scraper (latest mode)
        time_range (str | None): Filter articles by time range. Format: ISO8601/ISO8601.
        dedup_file (str | None): Path to previous output file for deduplication.
        **kwargs: Additional parameters (for future compatibility)

    Raises:
        ValidationError: For invalid input parameters
        NewsWatchError: For other newswatch-related errors
    """
    # validate output format
    if output_format.lower() not in ["csv", "xlsx", "json", "jsonl"]:
        raise ValidationError(
            f"Invalid output format: {output_format}. Use 'csv', 'xlsx', 'json', or 'jsonl'."
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
            keywords, start_date, scrapers, verbose, timeout, method, limit, max_pages,
            scraper_timeout=scraper_timeout, time_range=time_range, dedup_file=dedup_file, **kwargs
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
        elif output_format.lower() == "jsonl":
            # JSONL: write each record as a single JSON line (no pandas support)
            tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
            with open(tmp_path, mode="w", encoding="utf-8") as f:
                for _, row in df.iterrows():
                    record = row.to_dict()
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
            tmp_path.replace(output_path)
        else:
            df.to_csv(output_path, index=False, encoding="utf-8")

        print(f"Data written to {output_path}")

    except Exception as e:
        if isinstance(e, (ValidationError, NewsWatchError)):
            raise
        raise NewsWatchError(f"Error saving to file: {e}") from e


def list_scrapers(method: str = "search") -> List[str]:
    """
    Get list of available scrapers.

    Returns:
        List[str]: List of available scraper names
    """
    scraper_classes, _ = get_available_scrapers(method=method)
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


def latest(
    scrapers: str = "auto", verbose: bool = False, timeout: int = 300,
    limit: int | None = None, max_pages: int | None = None,
    *, scraper_timeout: int | None = None,
    time_range: str | None = None, dedup_file: str | None = None,
) -> List[Dict]:
    """Fetch latest articles for monitoring workflows."""
    return scrape(
        keywords=None,
        start_date=None,
        scrapers=scrapers,
        verbose=verbose,
        timeout=timeout,
        method="latest",
        limit=limit,
        max_pages=max_pages,
        scraper_timeout=scraper_timeout,
        time_range=time_range,
        dedup_file=dedup_file,
    )


def latest_to_dataframe(
    scrapers: str = "auto", verbose: bool = False, timeout: int = 300,
    limit: int | None = None, max_pages: int | None = None,
    *, scraper_timeout: int | None = None,
    time_range: str | None = None, dedup_file: str | None = None,
) -> pd.DataFrame:
    """Fetch latest articles and return them as a DataFrame."""
    return scrape_to_dataframe(
        keywords=None,
        start_date=None,
        scrapers=scrapers,
        verbose=verbose,
        timeout=timeout,
        method="latest",
        limit=limit,
        max_pages=max_pages,
        scraper_timeout=scraper_timeout,
        time_range=time_range,
        dedup_file=dedup_file,
    )


def latest_to_file(
    output_path: Union[str, Path],
    output_format: str = "xlsx",
    scrapers: str = "auto",
    verbose: bool = False,
    timeout: int = 300,
    limit: int | None = None,
    max_pages: int | None = None,
    *,
    scraper_timeout: int | None = None,
    time_range: str | None = None,
    dedup_file: str | None = None,
) -> None:
    """Fetch latest articles and save them directly to a file."""
    scrape_to_file(
        keywords=None,
        start_date=None,
        output_path=output_path,
        output_format=output_format,
        scrapers=scrapers,
        verbose=verbose,
        timeout=timeout,
        method="latest",
        limit=limit,
        max_pages=max_pages,
        scraper_timeout=scraper_timeout,
        time_range=time_range,
        dedup_file=dedup_file,
    )
