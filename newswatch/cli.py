import argparse
import asyncio
import logging
import platform
from datetime import datetime

from .main import main as run_main


def cli():
    base_scrapers = [
        # "bisnisindonesia",
        "bisnis",
        "bloombergtechnoz",
        "cnbcindonesia",
        "detik",
        "katadata",
        "kompas",
        "metronews",
        "viva",
        "tempo",
    ]

    is_linux = platform.system().lower() == "linux"
    non_linux_scrapers = [] if is_linux else ["kontan", "jawapos"]

    # base and platform-specific scrapers
    available_scrapers = base_scrapers + non_linux_scrapers
    available_scrapers_str = ",".join(available_scrapers)

    # main description with platform-specific notes
    description = (
        "News Watch - Scrape news articles from various Indonesian news websites.\n"
        f"Currently supports: {available_scrapers_str}.\n"
    )
    if is_linux:
        description += "Note: The 'kontan' and 'jawapos' scrapers are not available on Linux platforms due to known issues."

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
