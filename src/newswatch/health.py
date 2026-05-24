"""Per-run source health report — lightweight, no dashboard, no DB."""

import asyncio
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .main import get_available_scrapers

logger = logging.getLogger(__name__)

_DEFAULT_PROBE_TIMEOUT = 30
_DEFAULT_MAX_PAGES = 1
_DEFAULT_LIMIT = 1

async def _run_health_scraper(
    scraper, name: str, method: str, timeout: int, progress: bool
) -> Dict:
    """Run a single scraper for health probing and return a report record."""
    start = asyncio.get_event_loop().time()
    try:
        if timeout:
            await asyncio.wait_for(scraper.scrape(method=method), timeout=timeout)
        else:
            await scraper.scrape(method=method)
        elapsed = round(asyncio.get_event_loop().time() - start, 2)
        count = scraper._articles_collected
        if count == 0:
            return {
                "slug": name,
                "status": "no_results",
                "article_count": 0,
                "elapsed_seconds": elapsed,
                "error_type": None,
                "error_message": None,
            }
        return {
            "slug": name,
            "status": "ok",
            "article_count": count,
            "elapsed_seconds": elapsed,
            "error_type": None,
            "error_message": None,
        }
    except asyncio.TimeoutError:
        elapsed = round(asyncio.get_event_loop().time() - start, 2)
        return {
            "slug": name,
            "status": "timeout",
            "article_count": 0,
            "elapsed_seconds": elapsed,
            "error_type": "TimeoutError",
            "error_message": f"Exceeded {timeout}s timeout",
        }
    except Exception as e:
        elapsed = round(asyncio.get_event_loop().time() - start, 2)
        return {
            "slug": name,
            "status": "error",
            "article_count": 0,
            "elapsed_seconds": elapsed,
            "error_type": type(e).__name__,
            "error_message": str(e),
        }

async def _async_health_report(
    method: str = "latest",
    scrapers: str = "auto",
    scraper_timeout: int = _DEFAULT_PROBE_TIMEOUT,
    max_pages: int = _DEFAULT_MAX_PAGES,
    limit: int = _DEFAULT_LIMIT,
) -> List[Dict]:
    """Run health probes and return list of report records."""
    from .registry import get_stable_scrapers

    scraper_classes, _ = get_available_scrapers(method=method)

    if scrapers.lower() in ("all", "auto"):
        slugs_to_run = list(scraper_classes.keys())
    else:
        slugs_to_run = [s.strip().lower() for s in scrapers.split(",")]

    results: List[Dict] = []
    for slug in slugs_to_run:
        scraper_info = scraper_classes.get(slug)
        if not scraper_info:
            results.append({
                "slug": slug,
                "status": "unsupported",
                "article_count": 0,
                "elapsed_seconds": 0,
                "error_type": None,
                "error_message": f"Not available for {method} method",
            })
            continue

        entry = get_stable_scrapers().get(slug)
        if not entry:
            results.append({
                "slug": slug,
                "status": "skipped",
                "article_count": 0,
                "elapsed_seconds": 0,
                "error_type": None,
                "error_message": "Not in stable registry",
            })
            continue

        scraper_class = scraper_info["class"]
        scraper_params = dict(scraper_info.get("params", {}))
        scraper_instance = scraper_class(
            keywords="latest" if method == "latest" else entry.smoke_keyword,
            queue_=asyncio.Queue(),
            **scraper_params,
        )
        scraper_instance.max_latest_pages = max_pages
        instance_queue = scraper_instance.queue_

        items_collected = []

        async def _collect_from_queue(q, items):
            """Drain queue after scraper finishes; sentinel or timeout ends collection."""
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=5)
                    if item is None:
                        break
                    items.append(item)
                except asyncio.TimeoutError:
                    break
                except Exception:
                    break

        collector = asyncio.create_task(_collect_from_queue(instance_queue, items_collected))

        record = await _run_health_scraper(scraper_instance, slug, method, scraper_timeout, False)
        # Drain remaining items after scraper done
        try:
            await asyncio.wait_for(collector, timeout=15)
        except (asyncio.TimeoutError, Exception):
            collector.cancel()

        record["article_count"] = len(items_collected)
        if record["status"] == "no_results" and items_collected:
            record["status"] = "ok"

        # Add registry metadata
        record["name"] = entry.name
        record["method"] = method
        record["browser_required"] = entry.browser_required
        record["strict_search"] = entry.strict_search
        record["supports_search"] = entry.supports_search
        record["supports_latest"] = entry.supports_latest
        record["smoke_keyword"] = entry.smoke_keyword
        record["checked_at"] = datetime.now().isoformat()
        results.append(record)

    return results

def health_report(
    method: str = "latest",
    scrapers: str = "auto",
    scraper_timeout: int = _DEFAULT_PROBE_TIMEOUT,
    max_pages: int = _DEFAULT_MAX_PAGES,
    limit: int = _DEFAULT_LIMIT,
) -> List[Dict]:
    """Run health probes and return list of report records (sync API).

    Args:
        method: 'latest' or 'search'. Default 'latest'.
        scrapers: 'auto', 'all', or comma-separated slugs.
        scraper_timeout: per-scraper timeout in seconds.
        max_pages: max pages per scraper in latest mode.
        limit: max articles per scraper (for internal queue coordination).

    Returns:
        List of health record dicts with schema:
            slug, name, method, status, article_count, elapsed_seconds,
            error_type, error_message, browser_required, strict_search,
            supports_search, supports_latest, smoke_keyword, checked_at
    """
    try:
        return asyncio.run(
            _async_health_report(
                method=method,
                scrapers=scrapers,
                scraper_timeout=scraper_timeout,
                max_pages=max_pages,
                limit=limit,
            )
        )
    except KeyboardInterrupt:
        return []
    except Exception as e:
        logger.error(f"Health report failed: {e}")
        return []


def health_report_to_dataframe(report: List[Dict]) -> pd.DataFrame:
    """Convert health report list to pandas DataFrame."""
    if not report:
        return pd.DataFrame()
    return pd.DataFrame(report)


def health_report_to_file(
    report: List[Dict], output_path: str, output_format: str = "json"
) -> None:
    """Write health report to file.

    Args:
        report: health report list from health_report().
        output_path: output file path.
        output_format: 'json', 'csv', or 'xlsx'.
    """
    path = Path(output_path)
    fmt = output_format.lower()

    if fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        if report:
            fieldnames = list(report[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(report)
        else:
            path.touch()
    elif fmt == "xlsx":
        df = health_report_to_dataframe(report)
        df.to_excel(path, index=False)
    else:
        raise ValueError(f"Unsupported format: {fmt}. Use json, csv, or xlsx.")


def _print_health_summary(report: List[Dict]) -> None:
    """Print a human-readable health summary table to stdout."""
    if not report:
        print("No health data.")
        return

    # Table header
    fmt = "{:<20} {:<10} {:>5} {:>8} {}"
    print(fmt.format("SOURCE", "STATUS", "COUNT", "SEC", "ERROR"))
    print("-" * 72)

    for r in report:
        slug = r.get("slug", "?")[:19]
        status = r.get("status", "?")[:9]
        count = r.get("article_count", 0)
        elapsed = r.get("elapsed_seconds", 0)
        error = r.get("error_message") or ""
        if error and len(error) > 30:
            error = error[:27] + "..."
        print(fmt.format(slug, status, count, f"{elapsed:.1f}", error))

    print("-" * 72)
    total = len(report)
    ok = sum(1 for r in report if r.get("status") == "ok")
    err = sum(1 for r in report if r.get("status") == "error")
    timeout = sum(1 for r in report if r.get("status") == "timeout")
    no_res = sum(1 for r in report if r.get("status") == "no_results")
    print(f"Summary: {ok}/{total} OK, {no_res} no results, {timeout} timeouts, {err} errors")
