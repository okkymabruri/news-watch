"""
author: Okky Mabruri <okkymbrur@gmail.com>
maintainer: Okky Mabruri <okkymbrur@gmail.com>
"""

import asyncio
import csv
import logging
import platform
from datetime import datetime
from pathlib import Path

from .scrapers.bisnisindonesia import BisnisIndonesiaScraper
from .scrapers.cnbcindonesia import CNBCScraper
from .scrapers.detik import DetikScraper
from .scrapers.katadata import KatadataScraper
from .scrapers.kompas import KompasScraper
from .scrapers.kontan import KontanScraper
from .scrapers.viva import VivaScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
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

    current_time = datetime.now().strftime("%Y%m%d_%H")
    filename = Path.cwd() / f"news-watch-{keywords.replace(',','.')}-{current_time}.csv"

    try:
        with open(filename, mode="w", newline="", encoding="utf-8") as csvfile:
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

        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to CSV: {e}")


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
    current_time = datetime.now().strftime("%Y%m%d_%H")
    filename = (
        Path.cwd() / f"news-watch-{keywords.replace(',','.')}-{current_time}.xlsx"
    )
    items = []

    while True:
        item = await queue.get()
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


async def main(args):
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    keywords = args.keywords
    selected_scrapers = args.scrapers

    queue_ = asyncio.Queue()

    output_format = getattr(args, "output_format", "xlsx")
    if output_format.lower() == "xlsx":
        writer_task = asyncio.create_task(write_xlsx(queue_, args.keywords))
    else:
        writer_task = asyncio.create_task(write_csv(queue_, args.keywords))

    # mapping of scraper names to their corresponding classes and additional parameters
    scraper_classes = {
        "bisnisindonesia": {"class": BisnisIndonesiaScraper, "params": {}},
        "cnbc": {"class": CNBCScraper, "params": {}},
        "detik": {"class": DetikScraper, "params": {}},
        "katadata": {"class": KatadataScraper, "params": {}},
        "kompas": {"class": KompasScraper, "params": {}},
        "viva": {"class": VivaScraper, "params": {}},
        # FIX ME: add more scrapers here
        # FIX ME: add english website reuters, CNBC
    }

    # Exclude 'kontan' scraper if running on a Linux platform
    # Currently results in an error when run on the cloud due to Cloudflare ban
    # Limitation: can scrape a maximum of 50 pages
    if platform.system().lower() != "linux":
        scraper_classes["kontan"] = {"class": KontanScraper, "params": {}}

    if selected_scrapers.lower() == "all":
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
        return

    # run all scrapers concurrently
    await asyncio.gather(*(scraper.scrape() for scraper in scrapers))

    # ater scraping is done, put a sentinel value into the queue to signal the writer to finish
    await queue_.put(None)
    await writer_task
