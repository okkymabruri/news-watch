"""Per-run source health report — lightweight, no dashboard, no DB."""

import asyncio
import csv
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

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

    # Suppress logging during health probes
    logging.disable(logging.CRITICAL)

    scraper_classes = get_available_scrapers(method=method)

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
        elapsed_seconds = 0.0

        async def _run_and_collect():
            """Run scraper and collect queue items."""
            nonlocal elapsed_seconds
            start = asyncio.get_event_loop().time()

            # Phase 1: Run scraper - items go into queue during scraping
            run_result = await _run_health_scraper(scraper_instance, slug, method, scraper_timeout, False)
            elapsed_seconds = round(asyncio.get_event_loop().time() - start, 2)

            # Phase 2: Put sentinel (scraper.scrape() doesn't put it, only main.main() does)
            await instance_queue.put(None)

            # Phase 3: Drain queue until sentinel or limit
            collector_items = []
            while True:
                try:
                    item = await asyncio.wait_for(instance_queue.get(), timeout=5)
                    if item is None:  # sentinel
                        break
                    collector_items.append(item)
                    if limit is not None and len(collector_items) >= limit:
                        break
                except asyncio.TimeoutError:
                    break

            return collector_items, run_result

        items_collected, run_result = await _run_and_collect()

        # Determine final status: prefer collected count, else preserve timeout/error
        if items_collected:
            status = "ok"
            error_type = None
            error_message = None
        else:
            status = run_result.get("status", "no_results")
            error_type = run_result.get("error_type")
            error_message = run_result.get("error_message")

        record = {
            "slug": slug,
            "status": status,
            "article_count": len(items_collected),
            "elapsed_seconds": elapsed_seconds,
            "error_type": error_type,
            "error_message": error_message,
        }

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
    finally:
        logging.disable(logging.NOTSET)


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

    if fmt == "jsonl":
        with open(path, "w", encoding="utf-8") as f:
            for item in report:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    elif fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        if report:
            fieldnames = list(dict.fromkeys(k for row in report for k in row))
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
        raise ValueError(f"Unsupported format: {fmt}. Use json, jsonl, csv, or xlsx.")


def append_health_history(
    report: List[Dict],
    path: Union[str, Path],
    run_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> int:
    """Append a health report to a JSONL history file (append-only).

    Each source in the report becomes one JSONL line. The ``run_id`` and
    ``timestamp`` are shared across all lines of a single call so consumers
    can group by run.

    Safe on missing files (creates them) and missing parent directories
    (creates them). Existing content is preserved verbatim; corrupt lines
    are left untouched. ``json.dumps`` failures for individual records are
    logged and the record is skipped, so a single bad source cannot block
    the rest of the run from being persisted.

    Args:
        report: health report list from :func:`health_report`.
        path: JSONL file path. Created if missing. Parent dirs created if missing.
        run_id: optional run identifier (default: generated ``uuid4`` hex[:8]).
        timestamp: optional ISO 8601 timestamp (default: now).

    Returns:
        Number of records appended.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rid = run_id or uuid.uuid4().hex[:8]
    ts = timestamp or datetime.now().isoformat()

    count = 0
    with open(path, "a", encoding="utf-8") as f:
        for src in report:
            record = {
                "timestamp": ts,
                "run_id": rid,
                "source": src.get("slug"),
                "status": src.get("status"),
                "error": src.get("error_message"),
                "count": src.get("article_count", 0),
                "error_type": src.get("error_type"),
                "method": src.get("method"),
                "elapsed_seconds": src.get("elapsed_seconds"),
                "name": src.get("name"),
            }
            try:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
            except (TypeError, ValueError) as e:
                logger.warning(f"Skipping unserializable health record for {src.get('slug')!r}: {e}")
    return count


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
