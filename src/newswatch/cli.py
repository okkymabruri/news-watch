import argparse
import asyncio
import logging
import os
from datetime import datetime

from .config import get_health_history_path
from .main import get_available_scrapers
from .main import main as run_main
from .health import append_health_history, health_report, health_report_to_file, _print_health_summary


def cli():
    scraper_classes = get_available_scrapers(method="search")
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
        help="Maximum number of pages to fetch per scraper.",
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
        "--daterange",
        dest="time_range",
        type=str,
        default=None,
        help="Filter articles by inclusive date range. Format: YYYY-MM-DD/YYYY-MM-DD, e.g. '2026-07-13/2026-07-14'.",
    )
    parser.add_argument(
        "--dedup-file",
        type=str,
        default=None,
        help="Path to a previous output file (JSON/JSONL/CSV). Articles with matching links are skipped.",
    )
    parser.add_argument(
        "--health-report",
        action="store_true",
        help="Run health probes and print per-source status. Uses --method, --scrapers, --scraper-timeout, --max-pages.",
    )
    parser.add_argument(
        "--health-history",
        type=str,
        default=None,
        help="Append each per-source health record to this JSONL file (append-only). Also set via NEWSWATCH_HEALTH_HISTORY env.",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy URL for all requests (e.g. 'http://proxy.example.com:8080' or 'socks5://proxy.example.com:1080'). Also set via NEWSWATCH_PROXY env.",
    )
    args = parser.parse_args()


    if args.proxy:
        os.environ["NEWSWATCH_PROXY"] = args.proxy

    scraper_classes = get_available_scrapers(
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

    # Health report mode
    if args.health_report:
        report = health_report(
            method=args.method,
            scrapers=args.scrapers,
            scraper_timeout=args.scraper_timeout if args.scraper_timeout is not None else 30,
            max_pages=args.max_pages if args.max_pages is not None else 1,
            limit=args.limit if args.limit is not None else 1,
        )
        _print_health_summary(report)
        if args.output_path:
            health_report_to_file(report, args.output_path, args.output_format)
            print(f"Health report written to {args.output_path}")
        history_path = args.health_history or get_health_history_path()
        if history_path:
            n = append_health_history(report, history_path)
            print(f"Appended {n} health record(s) to {history_path}")
        return

    # By default, suppress all logging unless verbose or progress is specified
    if not args.verbose and not args.progress:
        logging.disable(logging.CRITICAL)

    asyncio.run(run_main(args))


if __name__ == "__main__":
    cli()
