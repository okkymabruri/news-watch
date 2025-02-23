import argparse
import asyncio
import logging
import platform
from datetime import datetime

from .main import main as run_main


def cli():
    # List of available scrapers based on the platform
    is_linux = platform.system().lower() == "linux"
    available_scrapers = [
        "bisnisindonesia",
        "bloombergtechnoz",
        "cnbcindonesia",
        "detik",
        "jawapos",
        "katadata",
        "kompas",
        "metronews",
        "viva",
        "tempo",
    ]
    if not is_linux:
        available_scrapers.append("kontan")
    available_scrapers_str = ",".join(available_scrapers)

    # main description with platform-specific notes
    description = (
        "News Watch - Scrape news articles from various Indonesian news websites.\n"
        f"Currently supports: {available_scrapers_str}.\n"
    )
    if is_linux:
        description += "Note: The 'kontan' scraper is not available on Linux platforms due to known issues."

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
        default="all",
        help="Comma-separated list of scrapers to use (e.g., 'kompas,viva'). Default is all.",
    )
    parser.add_argument(
        "--output_format",
        "-of",
        choices=["csv", "xlsx"],
        default="csv",
        type=str,
        help="Output file format. Options are csv or xlsx. Default is csv.",
    )
    parser.add_argument(
        "--silent",
        "-S",
        action="store_true",
        help="Suppress all logging output.",
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

    if args.silent:
        logging.disable(logging.CRITICAL)

    asyncio.run(run_main(args))


if __name__ == "__main__":
    cli()
