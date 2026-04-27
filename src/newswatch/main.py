"""
author: Okky Mabruri <okkymbrur@gmail.com>
maintainer: Okky Mabruri <okkymbrur@gmail.com>
"""

import asyncio
import csv
import json
import logging
import platform
from datetime import datetime
from pathlib import Path


from .registry import get_available_scrapers_from_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


def _build_output_label(keywords=None, method="search"):
    if method == "latest":
        return "latest"

    keywords = keywords or "news"
    keywords_list = keywords.split(",")
    if len(keywords_list) > 2:
        return ".".join(keywords_list[:2]) + "..."
    return ".".join(keywords_list)


async def write_csv(queue, output_label, filename=None):
    fieldnames = [
        "title",
        "publish_date",
        "author",
        "content",
        "keyword",
        "category",
        "source",
        "link",
    ]

    if filename is None:
        current_time = datetime.now().strftime("%Y%m%d_%H")
        filename = Path.cwd() / f"news-watch-{output_label}-{current_time}.csv"
    else:
        filename = Path(filename)

    tmp_filename = filename.with_suffix(filename.suffix + ".tmp")

    try:
        with open(tmp_filename, mode="w", newline="", encoding="utf-8") as csvfile:
            csv_writer = csv.DictWriter(
                csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL
            )
            csv_writer.writeheader()

            while True:
                item = await queue.get()
                if item is None:  # Sentinel value to stop the writer
                    break

                # Format datetime objects as strings
                if isinstance(item.get("publish_date"), datetime):
                    item["publish_date"] = item["publish_date"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                csv_writer.writerow(item)
                csvfile.flush()  # Ensure data is written to disk

        tmp_filename.replace(filename)
        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to CSV: {e}")


async def write_json(queue, output_label, filename=None):
    """Write scraped articles to JSON file format."""
    if filename is None:
        current_time = datetime.now().strftime("%Y%m%d_%H")
        filename = Path.cwd() / f"news-watch-{output_label}-{current_time}.json"
    else:
        filename = Path(filename)

    articles = []

    try:
        while True:
            item = await queue.get()
            if item is None:  # Sentinel value to stop the writer
                break

            # Format datetime objects as strings for JSON serialization
            if isinstance(item.get("publish_date"), datetime):
                item["publish_date"] = item["publish_date"].strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            articles.append(item)

        # Write all articles to JSON file
        with open(filename, mode="w", encoding="utf-8") as jsonfile:
            json.dump(articles, jsonfile, indent=2, ensure_ascii=False)

        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to JSON: {e}")


async def write_xlsx(queue, output_label, filename=None):
    import pandas as pd

    fieldnames = [
        "title",
        "publish_date",
        "author",
        "content",
        "keyword",
        "category",
        "source",
        "link",
    ]

    if filename is None:
        current_time = datetime.now().strftime("%Y%m%d_%H")
        filename = Path.cwd() / f"news-watch-{output_label}-{current_time}.xlsx"
    else:
        filename = Path(filename)

    items = []

    while True:
        try:
            # Add a timeout to avoid hanging indefinitely
            item = await asyncio.wait_for(queue.get(), timeout=30)
        except asyncio.TimeoutError:
            # If no items received for 30 seconds, break the loop
            logging.warning("No items received for 30 seconds, stopping writer")
            break
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                break
            else:
                raise

        if item is None:  # Sentinel value to stop
            break
        # Format datetime objects as strings
        if isinstance(item.get("publish_date"), datetime):
            item["publish_date"] = item["publish_date"].strftime("%Y-%m-%d %H:%M:%S")
        items.append(item)

    try:
        df = pd.DataFrame(items, columns=fieldnames)
        df.to_excel(filename, index=False)
        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to XLSX: {e}")


def get_available_scrapers(method="search"):
    """Get list of available scrapers from the central registry."""
    return get_available_scrapers_from_registry(method=method)


async def main(args):
    method = getattr(args, "method", "search")
    start_date = (
        datetime.strptime(args.start_date, "%Y-%m-%d")
        if method == "search" and args.start_date
        else None
    )
    keywords = (args.keywords or "ihsg") if method == "search" else "latest"
    selected_scrapers = args.scrapers
    max_pages = getattr(args, "max_pages", None)

    queue_ = asyncio.Queue()

    # Get custom output path if provided
    output_path = getattr(args, "output_path", None)
    output_label = _build_output_label(args.keywords, method)

    output_format = getattr(args, "output_format", "xlsx")
    if output_format.lower() == "xlsx":
        writer_task = asyncio.create_task(
            write_xlsx(queue_, output_label, output_path)
        )
    elif output_format.lower() == "json":
        writer_task = asyncio.create_task(
            write_json(queue_, output_label, output_path)
        )
    else:
        writer_task = asyncio.create_task(write_csv(queue_, output_label, output_path))

    scraper_classes, linux_excluded_scrapers = get_available_scrapers(method=method)

    force_all_scrapers = selected_scrapers.lower() == "all"

    if force_all_scrapers and platform.system().lower() == "linux":
        scraper_classes.update(linux_excluded_scrapers)
        logging.warning(
            f"Forcing all scrapers on Linux - may cause errors: {', '.join(linux_excluded_scrapers.keys())}"
        )
    elif platform.system().lower() == "linux":
        excluded_names = list(linux_excluded_scrapers.keys())
        logging.info(
            f"Running on Linux - excluded scrapers: {', '.join(excluded_names)}"
        )

    if selected_scrapers.lower() in ["all", "auto"]:
        scrapers_to_run = list(scraper_classes.keys())
    else:
        scrapers_to_run = [
            name.strip().lower() for name in selected_scrapers.split(",")
        ]

    scrapers = []
    for scraper_name in scrapers_to_run:
        scraper_info = scraper_classes.get(scraper_name)
        if scraper_info:
            scraper_class = scraper_info["class"]
            scraper_params = dict(scraper_info["params"])
            # Override max_latest_pages if caller specified max_pages
            if max_pages is not None:
                scraper_params["max_latest_pages"] = max_pages
            # instantiate scraper with possible special parameters
            scraper_instance = scraper_class(
                keywords, start_date=start_date, queue_=queue_, **scraper_params
            )
            scrapers.append(scraper_instance)
        else:
            logging.warning(f"scraper '{scraper_name}' is not recognized.")

    if not scrapers:
        logging.error("no valid scrapers selected. exiting.")
        # Make sure to cancel writer task
        writer_task.cancel()
        try:
            await writer_task
        except asyncio.CancelledError:
            pass
        return

    # run all scrapers concurrently with a timeout
    scraper_tasks: list[asyncio.Task] = []
    try:
        scraper_tasks = [
            asyncio.create_task(scraper.scrape(method=method)) for scraper in scrapers
        ]
        # Set overall timeout to 3 minutes for all scrapers
        await asyncio.wait_for(asyncio.gather(*scraper_tasks), timeout=180)
    except asyncio.TimeoutError:
        logging.warning("Scraping took too long and was stopped after 3 minutes")
        for t in scraper_tasks:
            t.cancel()
    except Exception as e:
        logging.error(f"Error during scraping: {e}")
        for t in scraper_tasks:
            t.cancel()
    finally:
        # Ensure scrapers are fully stopped (don't cancel unrelated tasks).
        if scraper_tasks:
            await asyncio.gather(*scraper_tasks, return_exceptions=True)

    # After scraping is done, put a sentinel value into the queue to signal the writer to finish
    await queue_.put(None)

    # Wait for the writer to finish with a timeout
    try:
        await asyncio.wait_for(writer_task, timeout=30)
    except asyncio.TimeoutError:
        logging.warning("Writer task took too long and was stopped")
        writer_task.cancel()
    except Exception as e:
        logging.error(f"Error in writer task: {e}")
        writer_task.cancel()
