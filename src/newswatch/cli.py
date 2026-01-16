import argparse
import asyncio
import logging
import platform
from datetime import datetime

from .main import get_available_scrapers
from .main import main as run_main


def cli():
    scraper_classes, linux_excluded_scrapers = get_available_scrapers()
    available_scrapers = list(scraper_classes.keys())
    available_scrapers_str = ",".join(available_scrapers)

    # main description with platform-specific notes
    description = (
        "News Watch - Scrape news articles from various Indonesian news websites.\n"
        f"Currently supports: {available_scrapers_str}.\n"
    )
    if platform.system().lower() == "linux":
        excluded_names = list(linux_excluded_scrapers.keys())
        description += f"Note: The '{', '.join(excluded_names)}' scrapers are not available on Linux platforms due to known issues."

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--keywords",
        "-k",
        default="ihsg",
        help="Comma-separated list of keywords to scrape (e.g., 'ojk,bank,npl')",
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
        choices=["csv", "xlsx", "json"],
        default="csv",
        type=str,
        help="Output file format. Options are csv, xlsx, or json. Default is csv.",
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
    args = parser.parse_args()

    if args.list_scrapers:
        print("Supported scrapers:\n- " + available_scrapers_str.replace(",", "\n- "))
        return

    # By default, suppress all logging unless verbose is specified
    if not args.verbose:
        logging.disable(logging.CRITICAL)

    asyncio.run(run_main(args))


if __name__ == "__main__":
    cli()
