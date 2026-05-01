import argparse
import asyncio
import logging
from datetime import datetime

from .main import get_available_scrapers
from .main import main as run_main


def cli():
    scraper_classes, _linux_excluded = get_available_scrapers(method="search")
    available_scrapers = list(scraper_classes.keys())
    available_scrapers_str = ",".join(available_scrapers)

    # main description with platform-specific notes
    description = (
        "News Watch - Scrape news articles from various Indonesian news websites.\n"
        f"Currently supports: {available_scrapers_str}.\n"
    )

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--method",
        choices=["search", "latest"],
        default="search",
        help="Retrieval method. 'search' uses keyword/date search. 'latest' fetches newest articles for near-realtime monitoring.",
    )
    parser.add_argument(
        "--keywords",
        "-k",
        default=None,
        help="Comma-separated list of keywords to scrape (e.g., 'ojk,bank,npl'). Default is 'ihsg' for search mode, unused in latest mode.",
    )
    parser.add_argument(
        "--start_date",
        "-sd",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Start date for scraping in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--scrapers",
        "-s",
        default="auto",
        help="Comma-separated list of scrapers to use (e.g., 'kompas,viva'). 'auto' uses platform-appropriate scrapers, 'all' forces all scrapers (may fail on some platforms).",
    )
    parser.add_argument(
        "--output_format",
        "-of",
        choices=["csv", "xlsx", "json", "jsonl"],
        default="csv",
        type=str,
        help="Output file format. Options are csv, xlsx, json, or jsonl. Default is csv.",
    )
    parser.add_argument(
        "--output_path",
        "-o",
        type=str,
        help="Custom output file path (e.g., 'news-watch-output.csv'). If not specified, uses default naming.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all logging output.",
    )
    parser.add_argument(
        "--list_scrapers",
        action="store_true",
        help="List supported scrapers.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of articles to collect in latest mode.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to fetch per scraper in latest mode.",
    )
    parser.add_argument(
        "--scraper-timeout",
        type=int,
        default=None,
        help="Per-scraper timeout in seconds. Scrapers exceeding this are cancelled.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print per-scraper progress lines (implies some verbosity).",
    )
    parser.add_argument(
        "--time-range",
        type=str,
        default=None,
        help="Filter articles by time range. Format: ISO8601/ISO8601, e.g. '2026-04-30T16:30:00/2026-05-01T08:00:00'.",
    )
    parser.add_argument(
        "--dedup-file",
        type=str,
        default=None,
        help="Path to a previous output file (JSON/JSONL/CSV). Articles with matching links are skipped.",
    )
    args = parser.parse_args()

    scraper_classes, _linux_excluded = get_available_scrapers(
        method=args.method
    )
    available_scrapers = list(scraper_classes.keys())
    available_scrapers_str = ",".join(available_scrapers)

    if args.list_scrapers:
        print(
            f"Supported {args.method} scrapers:\n- "
            + available_scrapers_str.replace(",", "\n- ")
        )
        return

    # By default, suppress all logging unless verbose or progress is specified
    if not args.verbose and not args.progress:
        logging.disable(logging.CRITICAL)

    asyncio.run(run_main(args))


if __name__ == "__main__":
    cli()
