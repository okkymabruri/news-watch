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

from .scrapers.antaranews import AntaranewsScraper
from .scrapers.bisnis import BisnisScraper
from .scrapers.bloombergtechnoz import BloombergTechnozScraper
from .scrapers.cnbcindonesia import CNBCScraper
from .scrapers.cnnindonesia import CNNIndonesiaScraper
from .scrapers.detik import DetikScraper
from .scrapers.jawapos import JawaposScraper
from .scrapers.katadata import KatadataScraper
from .scrapers.kompas import KompasScraper
from .scrapers.kontan import KontanScraper
from .scrapers.liputan6 import Liputan6Scraper
from .scrapers.merdeka import MerdekaScraper
from .scrapers.mediaindonesia import MediaIndonesiaScraper
from .scrapers.metrotvnews import MetrotvnewsScraper
from .scrapers.okezone import OkezoneScraper
from .scrapers.republika import RepublikaScraper
from .scrapers.suara import SuaraScraper
from .scrapers.tempo import TempoScraper
from .scrapers.tirto import TirtoScraper
from .scrapers.tribunnews import TribunnewsScraper
from .scrapers.viva import VivaScraper
from .scrapers.idntimes import IDNTimesScraper
from .scrapers.kumparan import KumparanScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


async def write_csv(queue, keywords, filename=None):
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
        keywords_list = keywords.split(",")
        if len(keywords_list) > 2:
            keywords_short = ".".join(keywords_list[:2]) + "..."
        else:
            keywords_short = ".".join(keywords_list)
        filename = Path.cwd() / f"news-watch-{keywords_short}-{current_time}.csv"
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


async def write_json(queue, keywords, filename=None):
    """Write scraped articles to JSON file format."""
    if filename is None:
        current_time = datetime.now().strftime("%Y%m%d_%H")
        keywords_list = keywords.split(",")
        if len(keywords_list) > 2:
            keywords_short = ".".join(keywords_list[:2]) + "..."
        else:
            keywords_short = ".".join(keywords_list)
        filename = Path.cwd() / f"news-watch-{keywords_short}-{current_time}.json"
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


async def write_xlsx(queue, keywords, filename=None):
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
        keywords_list = keywords.split(",")
        if len(keywords_list) > 2:
            keywords_short = ".".join(keywords_list[:2]) + "..."
        else:
            keywords_short = ".".join(keywords_list)
        filename = Path.cwd() / f"news-watch-{keywords_short}-{current_time}.xlsx"
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


def get_available_scrapers():
    """Get list of available scrapers based on platform"""
    # mapping of scraper names to their corresponding classes and additional parameters
    scraper_classes = {
        "antaranews": {"class": AntaranewsScraper, "params": {"concurrency": 7}},
        "bisnis": {"class": BisnisScraper, "params": {"concurrency": 5}},
        "bloombergtechnoz": {"class": BloombergTechnozScraper, "params": {}},
        "cnbcindonesia": {"class": CNBCScraper, "params": {"concurrency": 5}},
        "cnnindonesia": {"class": CNNIndonesiaScraper, "params": {"concurrency": 5}},
        "detik": {"class": DetikScraper, "params": {"concurrency": 5}},
        "idntimes": {"class": IDNTimesScraper, "params": {"concurrency": 7}},
        "jawapos": {"class": JawaposScraper, "params": {"concurrency": 5}},
        "kontan": {"class": KontanScraper, "params": {}},
        "kompas": {"class": KompasScraper, "params": {"concurrency": 7}},
        "kumparan": {"class": KumparanScraper, "params": {"concurrency": 5}},
        "liputan6": {"class": Liputan6Scraper, "params": {"concurrency": 5}},
        "merdeka": {"class": MerdekaScraper, "params": {"concurrency": 7}},
        "metrotvnews": {"class": MetrotvnewsScraper, "params": {"concurrency": 2}},
        "okezone": {"class": OkezoneScraper, "params": {"concurrency": 7}},
        "republika": {"class": RepublikaScraper, "params": {"concurrency": 7}},
        "suara": {"class": SuaraScraper, "params": {"concurrency": 12}},
        "tempo": {"class": TempoScraper, "params": {"concurrency": 1}},
        "tirto": {"class": TirtoScraper, "params": {"concurrency": 5}},
        "tribunnews": {"class": TribunnewsScraper, "params": {"concurrency": 5}},
        "viva": {"class": VivaScraper, "params": {"concurrency": 7}},
        "mediaindonesia": {"class": MediaIndonesiaScraper, "params": {}},
        # FIX ME: add more scrapers here
        # FIX ME: add english website reuters, CNBC
    }

    # Excluded on Linux/cloud by default (often requires browser token capture).
    linux_excluded_scrapers = {
        "katadata": {"class": KatadataScraper, "params": {}},
    }

    if platform.system().lower() != "linux":
        scraper_classes.update(linux_excluded_scrapers)

    return scraper_classes, linux_excluded_scrapers


async def main(args):
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    keywords = args.keywords
    selected_scrapers = args.scrapers

    queue_ = asyncio.Queue()

    # Get custom output path if provided
    output_path = getattr(args, "output_path", None)

    output_format = getattr(args, "output_format", "xlsx")
    if output_format.lower() == "xlsx":
        writer_task = asyncio.create_task(
            write_xlsx(queue_, args.keywords, output_path)
        )
    elif output_format.lower() == "json":
        writer_task = asyncio.create_task(
            write_json(queue_, args.keywords, output_path)
        )
    else:
        writer_task = asyncio.create_task(write_csv(queue_, args.keywords, output_path))

    scraper_classes, linux_excluded_scrapers = get_available_scrapers()

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
            scraper_params = scraper_info["params"]
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
        scraper_tasks = [asyncio.create_task(scraper.scrape()) for scraper in scrapers]
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
