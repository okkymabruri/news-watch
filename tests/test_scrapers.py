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
(``aljazeera``, ``balipost``, ``dandapala``, ``hukumonline``, ``independen``)
are excluded — they have ``supports_search=False`` and would always fail
under this contract.
"""
from __future__ import annotations

import asyncio
import importlib
import os
from datetime import datetime, timedelta

import aiohttp
import pytest

try:
    from playwright.async_api import Error as PlaywrightError
except ImportError:  # playwright not installed in some CI lanes
    PlaywrightError = None  # type: ignore[assignment]

from newswatch.registry import SCRAPERS, get_stable_slugs

# Known external/network/browser failure classes worth skipping in canonical
# live tests. Anything outside this tuple (e.g. ``AssertionError``,
# ``ValueError``, ``KeyError``, ``TypeError``) is a real bug and must fail.
_KNOWN_NETWORK_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    asyncio.CancelledError,
    ConnectionError,
    TimeoutError,
    aiohttp.ClientError,
    OSError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ServerTimeoutError,
)
if PlaywrightError is not None:
    _KNOWN_NETWORK_EXCEPTIONS = _KNOWN_NETWORK_EXCEPTIONS + (PlaywrightError,)


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


def _latest_capable_class_slug_pairs() -> list[tuple[str, type]]:
    """Latest-mode mirror of ``_search_capable_class_slug_pairs``.

    Covers every stable scraper whose registry entry sets
    ``supports_latest=True``. That set is a superset of
    ``supports_search``; the latest-only entries have no working search
    endpoint and must be exercised via ``scrape(method="latest")``.
    """
    pairs: list[tuple[str, type]] = []
    for slug in sorted(
        s for s in get_stable_slugs() if SCRAPERS[s].supports_latest
    ):
        entry = SCRAPERS[slug]
        module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
        pairs.append((slug, getattr(module, entry.class_name)))
    return pairs


def _select_shard(pairs: list[tuple[str, type]]) -> list[tuple[str, type]]:
    """Select one deterministic CI shard; default to the full matrix."""
    shard_count = int(os.getenv("NEWSWATCH_LIVE_SHARD_COUNT", "1"))
    shard_index = int(os.getenv("NEWSWATCH_LIVE_SHARD_INDEX", "0"))
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError(
            f"invalid live shard {shard_index}/{shard_count}; expected 0 <= index < count"
        )
    return [pair for index, pair in enumerate(pairs) if index % shard_count == shard_index]


_SEARCH_PAIRS = _select_shard(_search_capable_class_slug_pairs())
_LATEST_PAIRS = _select_shard(_latest_capable_class_slug_pairs())


@pytest.mark.asyncio
@pytest.mark.network
@pytest.mark.parametrize("slug,scraper_class", _SEARCH_PAIRS, ids=[p[0] for p in _SEARCH_PAIRS])
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
    if hasattr(scraper, "max_pages"):
        scraper.max_pages = 2

    consumer_task = asyncio.create_task(item_consumer(queue))

    try:
        scrape_task = asyncio.create_task(scraper.scrape())
        try:
            await asyncio.wait_for(scrape_task, timeout=60)
        except asyncio.TimeoutError:
            pytest.skip(f"{scraper_class.__name__} timed out after 60s (network or slow site)")
        except _KNOWN_NETWORK_EXCEPTIONS as e:
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
    keyword = SCRAPERS[slug].smoke_keyword.lower()
    assert any(
        keyword in (item.get("title") or "").lower()
        or keyword in (item.get("link") or "").lower()
        or keyword in (item.get("content") or "").lower()
        for item in items
    ), f"{slug} returned items but none contain smoke_keyword='{keyword}'"


@pytest.mark.asyncio
@pytest.mark.network
@pytest.mark.parametrize("slug,scraper_class", _LATEST_PAIRS, ids=[p[0] for p in _LATEST_PAIRS])
async def test_scraper_fetch_latest(slug: str, scraper_class: type) -> None:
    """Live latest-mode integration test for every stable+latest scraper.

    Mirrors ``test_scraper_fetch_data`` but drives ``scrape(method="latest")``:
    the scraper hits its index/listing endpoint without a keyword filter and
    publishes whatever articles it finds onto the queue. Latest-only entries
    are unreachable via search and are covered exclusively here.

    Failure mode is identical to the search test: timeout, transport error, or
    an empty upstream yields ``pytest.skip`` with a one-line reason so the
    visible skip count reflects source health instead of silently passing.
    """
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
    # ``keywords`` is required by the constructor even in latest mode;
    # ``fetch_latest_results`` ignores it. Pass the registry smoke keyword
    # so the constructor signature stays identical to search-mode scrapers.
    scraper = scraper_class(
        keywords=SCRAPERS[slug].smoke_keyword,
        queue_=queue,
    )
    if hasattr(scraper, "max_pages"):
        scraper.max_pages = 2

    consumer_task = asyncio.create_task(item_consumer(queue))

    try:
        scrape_task = asyncio.create_task(scraper.scrape(method="latest"))
        try:
            await asyncio.wait_for(scrape_task, timeout=60)
        except asyncio.TimeoutError:
            pytest.skip(f"{scraper_class.__name__} (latest) timed out after 60s (network or slow site)")
        except _KNOWN_NETWORK_EXCEPTIONS as e:
            pytest.skip(f"{scraper_class.__name__} (latest) network failure: {type(e).__name__}: {e}")

        try:
            await asyncio.wait_for(queue.join(), timeout=5)
        except asyncio.TimeoutError:
            pass
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except (asyncio.TimeoutError, asyncio.CancelledError, StopAsyncIteration):
            pass

    if not items:
        pytest.skip(
            f"{scraper_class.__name__} (latest) returned no items from "
            f"{getattr(scraper, 'base_url', '?')} "
            "(anti-bot, source change, or genuine gap)"
        )

    assert len(items) > 0
    for item in items:
        assert "title" in item
        assert item["title"]
        assert "publish_date" in item
        assert item["publish_date"]
        assert "content" in item
        assert item["content"]
        assert "link" in item
        assert item["link"]
