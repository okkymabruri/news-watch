"""
author: Okky Mabruri <okkymbrur@gmail.com>
maintainer: Okky Mabruri <okkymbrur@gmail.com>
"""

import asyncio
import csv
import json
import logging
from datetime import datetime
from pathlib import Path


from .registry import get_available_scrapers_from_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


def _load_dedup_links(file_path: str) -> set:
    """Load article links from a previous output file for deduplication."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    links = set()

    if suffix == ".csv":
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                link = row.get("link", "")
                if link:
                    links.add(link)
    elif suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            link = item.get("link", "")
            if link:
                links.add(link)
    elif suffix == ".jsonl":
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    item = json.loads(line)
                    link = item.get("link", "")
                    if link:
                        links.add(link)
    else:
        raise ValueError(
            f"Unsupported dedup file format: {suffix}. Use .csv, .json, or .jsonl."
        )

    logger.info(f"Loaded {len(links)} links from dedup file: {file_path}")
    return links


def _parse_time_range(time_range: str):
    """Parse time range string into start and end datetime objects.

    Format: ISO8601/ISO8601, e.g. '2026-04-30T16:30:00/2026-05-01T08:00:00'.
    """
    parts = time_range.split("/")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid time range format: {time_range}. Expected ISO8601/ISO8601."
        )

    start_dt = datetime.fromisoformat(parts[0])
    end_dt = datetime.fromisoformat(parts[1])

    return start_dt, end_dt


def _build_output_label(keywords=None, method="search"):
    if method == "latest":
        return "latest"

    keywords = keywords or "news"
    keywords_list = keywords.split(",")
    if len(keywords_list) > 2:
        return ".".join(keywords_list[:2]) + "..."
    return ".".join(keywords_list)


async def write_csv(queue, output_label, filename=None, limit=None, limit_reached_event=None, dedup_links=None, time_range=None):
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
    items_written = 0

    # Parse time range if provided
    time_start, time_end = (None, None)
    if time_range:
        time_start, time_end = time_range

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

                # Format datetime objects as strings
                if isinstance(item.get("publish_date"), datetime):
                    item["publish_date"] = item["publish_date"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                csv_writer.writerow(item)
                csvfile.flush()  # Ensure data is written to disk
                items_written += 1

                if limit is not None and items_written >= limit:
                    if limit_reached_event:
                        limit_reached_event.set()
                    break

        tmp_filename.replace(filename)
        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to CSV: {e}")


async def write_json(queue, output_label, filename=None, limit=None, limit_reached_event=None, dedup_links=None, time_range=None):
    """Write scraped articles to JSON file format."""
    if filename is None:
        current_time = datetime.now().strftime("%Y%m%d_%H")
        filename = Path.cwd() / f"news-watch-{output_label}-{current_time}.json"
    else:
        filename = Path(filename)

    articles = []
    items_written = 0

    # Parse time range if provided
    time_start, time_end = (None, None)
    if time_range:
        time_start, time_end = time_range

    try:
        while True:
            item = await queue.get()
            if item is None:  # Sentinel value to stop the writer
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

            # Format datetime objects as strings for JSON serialization
            if isinstance(item.get("publish_date"), datetime):
                item["publish_date"] = item["publish_date"].strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            articles.append(item)
            items_written += 1

            if limit is not None and items_written >= limit:
                if limit_reached_event:
                    limit_reached_event.set()
                break

        # Write all articles to JSON file
        with open(filename, mode="w", encoding="utf-8") as jsonfile:
            json.dump(articles, jsonfile, indent=2, ensure_ascii=False)

        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to JSON: {e}")


async def write_xlsx(queue, output_label, filename=None, limit=None, limit_reached_event=None, dedup_links=None, time_range=None):
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
    items_written = 0

    # Parse time range if provided
    time_start, time_end = (None, None)
    if time_range:
        time_start, time_end = time_range

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

        # Format datetime objects as strings
        if isinstance(item.get("publish_date"), datetime):
            item["publish_date"] = item["publish_date"].strftime("%Y-%m-%d %H:%M:%S")
        items.append(item)
        items_written += 1

        if limit is not None and items_written >= limit:
            if limit_reached_event:
                limit_reached_event.set()
            break

    try:
        df = pd.DataFrame(items, columns=fieldnames)
        df.to_excel(filename, index=False)
        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to XLSX: {e}")


async def write_jsonl(queue, output_label, filename=None, limit=None, limit_reached_event=None, dedup_links=None, time_range=None):
    """Write each article as a JSON line (JSONL) — crash-safe streaming output."""
    if filename is None:
        current_time = datetime.now().strftime("%Y%m%d_%H")
        filename = Path.cwd() / f"news-watch-{output_label}-{current_time}.jsonl"
    else:
        filename = Path(filename)

    tmp_filename = filename.with_suffix(filename.suffix + ".tmp")
    items_written = 0

    # Parse time range if provided
    time_start, time_end = (None, None)
    if time_range:
        time_start, time_end = time_range

    try:
        with open(tmp_filename, mode="w", encoding="utf-8") as f:
            while True:
                item = await queue.get()
                if item is None:  # Sentinel value to stop the writer
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

                # Format datetime objects as strings
                if isinstance(item.get("publish_date"), datetime):
                    item["publish_date"] = item["publish_date"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                f.flush()  # Ensure data is written to disk
                items_written += 1

                if limit is not None and items_written >= limit:
                    if limit_reached_event:
                        limit_reached_event.set()
                    break

        tmp_filename.replace(filename)
        print(f"Data written to {filename}")
    except Exception as e:
        logging.error(f"Error writing to JSONL: {e}")


def get_available_scrapers(method="search"):
    """Get list of available scrapers from the central registry."""
    return get_available_scrapers_from_registry(method=method)


async def _run_scraper_with_timeout(
    scraper, name, index, total, method, timeout, progress
):
    """Run a single scraper with optional timeout and progress logging."""
    if progress:
        print(f"[{index}/{total}] {name}: starting")
    start_time = asyncio.get_event_loop().time()
    try:
        if timeout:
            await asyncio.wait_for(scraper.scrape(method=method), timeout=timeout)
        else:
            await scraper.scrape(method=method)
        elapsed = asyncio.get_event_loop().time() - start_time
        if progress:
            print(f"[{index}/{total}] {name}: done in {elapsed:.1f}s")
        return "ok"
    except asyncio.TimeoutError:
        if progress:
            print(f"[{index}/{total}] {name}: timed out after {timeout}s")
        return "timeout"
    except Exception as e:
        elapsed = asyncio.get_event_loop().time() - start_time
        if progress:
            print(f"[{index}/{total}] {name}: error in {elapsed:.1f}s - {e}")
        return "error"


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
    limit = getattr(args, "limit", None)

    queue_ = asyncio.Queue()
    limit_reached_event = asyncio.Event()

    # Get custom output path if provided
    output_path = getattr(args, "output_path", None)
    output_label = _build_output_label(args.keywords, method)

    # Handle dedup file
    dedup_file = getattr(args, "dedup_file", None)
    dedup_links = None
    if dedup_file:
        try:
            dedup_links = _load_dedup_links(dedup_file)
        except Exception as e:
            logging.error(f"Failed to load dedup file: {e}")
            return

    # Handle time range
    time_range_str = getattr(args, "time_range", None)
    parsed_time_range = None
    if time_range_str:
        try:
            parsed_time_range = _parse_time_range(time_range_str)
        except Exception as e:
            logging.error(f"Failed to parse time range: {e}")
            return

    output_format = getattr(args, "output_format", "xlsx")
    if output_format.lower() == "xlsx":
        writer_task = asyncio.create_task(
            write_xlsx(queue_, output_label, output_path, limit=limit, limit_reached_event=limit_reached_event,
                       dedup_links=dedup_links, time_range=parsed_time_range)
        )
    elif output_format.lower() == "json":
        writer_task = asyncio.create_task(
            write_json(queue_, output_label, output_path, limit=limit, limit_reached_event=limit_reached_event,
                       dedup_links=dedup_links, time_range=parsed_time_range)
        )
    elif output_format.lower() == "jsonl":
        writer_task = asyncio.create_task(
            write_jsonl(queue_, output_label, output_path, limit=limit, limit_reached_event=limit_reached_event,
                        dedup_links=dedup_links, time_range=parsed_time_range)
        )
    else:
        writer_task = asyncio.create_task(
            write_csv(queue_, output_label, output_path, limit=limit, limit_reached_event=limit_reached_event,
                      dedup_links=dedup_links, time_range=parsed_time_range)
        )

    scraper_classes, _linux_excluded = get_available_scrapers(method=method)

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
            # instantiate scraper with possible special parameters
            scraper_instance = scraper_class(
                keywords, start_date=start_date, queue_=queue_, **scraper_params
            )
            # Apply max_pages limit for latest mode
            if max_pages is not None:
                scraper_instance.max_latest_pages = max_pages
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

    # Extract new CLI parameters
    scraper_timeout = getattr(args, "scraper_timeout", None)
    progress = getattr(args, "progress", False)

    # run all scrapers concurrently with per-scraper timeout and progress logging
    scraper_names = list(scraper_classes.keys()) if selected_scrapers.lower() in ["all", "auto"] else scrapers_to_run
    total = len(scrapers)
    progress_tasks = [
        asyncio.create_task(
            _run_scraper_with_timeout(
                scraper,
                scraper_names[i] if i < len(scraper_names) else f"scraper_{i}",
                i + 1,
                total,
                method,
                scraper_timeout,
                progress,
            )
        )
        for i, scraper in enumerate(scrapers)
    ]

    if limit is not None:
        all_done = asyncio.gather(*progress_tasks)
        limit_hit = asyncio.create_task(limit_reached_event.wait())
        done, pending = await asyncio.wait(
            [all_done, limit_hit], timeout=180, return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            all_done.cancel()
            for t in progress_tasks:
                if not t.done():
                    t.cancel()
            logging.warning("Scraping took too long and was stopped after 180 seconds")
        elif limit_hit in done:
            all_done.cancel()
            for t in progress_tasks:
                if not t.done():
                    t.cancel()
        else:
            limit_hit.cancel()
        await asyncio.gather(*progress_tasks, return_exceptions=True)
        # Collect results
        results = []
        for t in progress_tasks:
            if t.done() and not t.cancelled():
                results.append(t.result())
            else:
                results.append("cancelled")
    else:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*progress_tasks), timeout=180
            )
        except asyncio.TimeoutError:
            logging.warning("Scraping took too long and was stopped after 180 seconds")
            for t in progress_tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*progress_tasks, return_exceptions=True)
            results = []
            for t in progress_tasks:
                if t.done() and not t.cancelled():
                    results.append(t.result())
                else:
                    results.append("timeout")
        except Exception as e:
            logging.error(f"Error during scraping: {e}")
            results = []
            for t in progress_tasks:
                if t.done() and not t.cancelled():
                    results.append(t.result())
                else:
                    results.append("error")

    # Print summary if progress is enabled
    if progress and results:
        succeeded = results.count("ok")
        timed_out = results.count("timeout")
        errors = len(results) - succeeded - timed_out
        print(f"Summary: {succeeded} succeeded, {timed_out} timed out, {errors} errors")

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
