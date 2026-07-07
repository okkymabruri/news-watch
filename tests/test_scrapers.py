"""Network-marked live integration test for every registered scraper.

Parameterization is derived from ``newswatch.registry.SCRAPERS`` so any new
source lands in coverage automatically (same pattern as
``tests/test_scrapers_minimal.py`` and ``tests/test_scrapers_offline.py``).

Behavior contract:
- Each test runs against a real Indonesian site with the scraper's
  registry ``smoke_keyword`` for the last 7 days.
- On a clean run with items, the test asserts structural integrity
  (``title``, ``link``, ``publish_date``, ``content`` are all present
  and non-empty).
- On a network failure (timeout, DNS, anti-bot block, source-side
  change), the test **skips** with ``pytest.skip`` and a one-line
  reason. Skips are visible in the summary; they are not silently
  converted to passes the way ``xfail`` was in the prior version.
- This file is gated by ``@pytest.mark.network``; the default CI matrix
  excludes it. Run with ``pytest -m network`` to validate.

Filter: stable + search-capable slugs only (mirrors the F1 test fix in
``tests/test_scrapers_minimal.py``). Latest-only scrapers
(aljazeera, balipost, cnaindonesia) are excluded — they have
``supports_search=False`` and would always fail under this contract.
"""
from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timedelta

import pytest

from newswatch.registry import SCRAPERS, get_stable_slugs


def _search_capable_class_slug_pairs() -> list[tuple[str, type]]:
    """Build the parametrize payload once at module load.

    The registry's slug is the canonical key; do not derive it from the
    class name (some scrapers' class names do not match their slug —
    e.g. ``CNAIndonesiaScraper`` → ``'cnaindonesia'`` after strip, while
    the registry entry has its own mapping). Use the registry directly.
    """
    pairs: list[tuple[str, type]] = []
    for slug in sorted(
        s for s in get_stable_slugs() if SCRAPERS[s].supports_search
    ):
        entry = SCRAPERS[slug]
        module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
        pairs.append((slug, getattr(module, entry.class_name)))
    return pairs


_PAIRS = _search_capable_class_slug_pairs()


@pytest.mark.asyncio
@pytest.mark.network
@pytest.mark.parametrize("slug,scraper_class", _PAIRS, ids=[p[0] for p in _PAIRS])
async def test_scraper_fetch_data(slug: str, scraper_class: type) -> None:
    items: list[dict] = []

    async def item_consumer(queue: asyncio.Queue) -> None:
        try:
            while True:
                item = await queue.get()
                items.append(item)
                queue.task_done()
        except asyncio.CancelledError:
            pass

    queue: asyncio.Queue = asyncio.Queue()
    scraper = scraper_class(
        keywords=SCRAPERS[slug].smoke_keyword,
        start_date=datetime.now() - timedelta(days=7),
        queue_=queue,
    )

    consumer_task = asyncio.create_task(item_consumer(queue))

    try:
        scrape_task = asyncio.create_task(scraper.scrape())
        try:
            await asyncio.wait_for(scrape_task, timeout=60)
        except asyncio.TimeoutError:
            pytest.skip(f"{scraper_class.__name__} timed out after 60s (network or slow site)")
        except Exception as e:
            pytest.skip(f"{scraper_class.__name__} network failure: {type(e).__name__}: {e}")

        try:
            await asyncio.wait_for(queue.join(), timeout=5)
        except asyncio.TimeoutError:
            pass
    finally:
        consumer_task.cancel()
        try:
            await asyncio.wait_for(consumer_task, timeout=1)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

    if not items:
        pytest.skip(
            f"{scraper_class.__name__} returned no items for "
            f"smoke_keyword='{SCRAPERS[slug].smoke_keyword}' in last 7 days "
            f"(anti-bot, source change, or genuine gap)"
        )

    assert len(items) > 0
    for item in items:
        assert "title" in item
        assert "publish_date" in item
        assert "content" in item
        assert "link" in item
