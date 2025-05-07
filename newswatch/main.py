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

# from .scrapers.bisnisindonesia import BisnisIndonesiaScraper
from .scrapers.bisnis import BisnisScraper
from .scrapers.bloombergtechnoz import BloombergTechnozScraper
from .scrapers.cnbcindonesia import CNBCScraper
from .scrapers.detik import DetikScraper
from .scrapers.jawapos import JawaposScraper
from .scrapers.katadata import KatadataScraper
from .scrapers.kompas import KompasScraper
from .scrapers.kontan import KontanScraper
from .scrapers.metrotvnews import MetrotvnewsScraper
from .scrapers.tempo import TempoScraper
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
    keywords_list = keywords.split(",")
    if len(keywords_list) > 2:
        keywords_short = ".".join(keywords_list[:2]) + "..."
    else:
        keywords_short = ".".join(keywords_list)
    filename = Path.cwd() / f"news-watch-{keywords_short}-{current_time}.csv"

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
    keywords_list = keywords.split(",")
    if len(keywords_list) > 2:
        keywords_short = ".".join(keywords_list[:2]) + "..."
    else:
        keywords_short = ".".join(keywords_list)
    filename = Path.cwd() / f"news-watch-{keywords_short}-{current_time}.xlsx"

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
        # FIX ME: fix bisnisindonesia scraper
        # "bisnisindonesia": {"class": BisnisIndonesiaScraper, "params": {}},
        "bloombergtechnoz": {"class": BloombergTechnozScraper, "params": {}},
        "cnbcindonesia": {"class": CNBCScraper, "params": {}},
        "detik": {"class": DetikScraper, "params": {}},
        "katadata": {"class": KatadataScraper, "params": {}},
        "kompas": {"class": KompasScraper, "params": {}},
        "metrotvnews": {"class": MetrotvnewsScraper, "params": {}},
        "viva": {"class": VivaScraper, "params": {}},
        "tempo": {"class": TempoScraper, "params": {}},
        # FIX ME: add more scrapers here
        # FIX ME: add english website reuters, CNBC
    }

    # Exclude 'kontan' scraper if running on a Linux platform
    # Currently results in an error when run on the cloud due to Cloudflare ban
    # Limitation: can scrape a maximum of 50 pages
    if platform.system().lower() != "linux":
        scraper_classes["bisnis"] = {"class": BisnisScraper, "params": {}} # switch to bisnis.com from bisnisindonesia
        scraper_classes["kontan"] = {"class": KontanScraper, "params": {}}
        scraper_classes["jawapos"] = {"class": JawaposScraper, "params": {}}

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
        # Make sure to cancel writer task
        writer_task.cancel()
        try:
            await writer_task
        except asyncio.CancelledError:
            pass
        return

    # run all scrapers concurrently with a timeout
    try:
        scraper_tasks = [asyncio.create_task(scraper.scrape()) for scraper in scrapers]
        # Set overall timeout to 3 minutes for all scrapers
        await asyncio.wait_for(asyncio.gather(*scraper_tasks), timeout=180)
    except asyncio.TimeoutError:
        logging.warning("Scraping took too long and was stopped after 3 minutes")
    except Exception as e:
        logging.error(f"Error during scraping: {e}")
    finally:
        # Cancel any remaining scraper tasks
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task() and task is not writer_task:
                task.cancel()

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
