"""Offline (no-network) coverage for every registered scraper.

Derives the parameterization from ``newswatch.registry.SCRAPERS`` so any new
source lands in coverage automatically. Uses ``aioresponses`` to mock the
HTTP layer; the scraper code under test is unchanged.

Layers:
1. **Registry sanity** — every stable, search-capable scraper can be
   imported and instantiated with its registry smoke keyword.
2. **Parse contract** — given a canned HTML body, the full
   ``build_search_url`` → ``fetch`` → ``parse_article_links`` pipeline
   works end-to-end without raising. The real ``build_search_url``
   executes so adapter-specific state (e.g. ``gatra._current_keyword``)
   is initialized naturally; aioresponses intercepts whatever URL
   emerges with a regex match.
3. **Latest contract** — latest-mode scrapers that use the shared HTTP
   layer run through ``fetch_latest_results`` with mocked HTTP. Browser-
   required latest scrapers are visibly skipped because aioresponses
   cannot intercept Playwright/CDP traffic.
4. **Block detection** — ``_looks_blocked`` must keep flagging the
   canonical WAF/CDN markers.

These tests do NOT validate that a real Indonesian site returns real
articles. That's what ``tests/test_scrapers.py`` (network-marked) covers.
This file gives every scraper a deterministic, fast unit test that
catches regressions in the parsing layer without touching the network.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import importlib
import re

import pytest
from aioresponses import aioresponses

from newswatch.registry import SCRAPERS, get_stable_slugs
from newswatch.utils import _looks_blocked


# ── Parameterization helpers ───────────────────────────────────────────────


def _search_capable_slugs() -> list[str]:
    """All stable, search-capable slugs. Mirrors the F1 filter."""
    return sorted(
        slug for slug in get_stable_slugs() if SCRAPERS[slug].supports_search
    )


def _latest_capable_slugs() -> list[str]:
    """All stable, latest-capable slugs."""
    return sorted(
        slug for slug in get_stable_slugs() if SCRAPERS[slug].supports_latest
    )


def _import_scraper_class(slug: str):
    """Import the scraper class for ``slug`` from the registry."""
    entry = SCRAPERS[slug]
    module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
    return getattr(module, entry.class_name)


_PASSTHROUGH_HTML = (
    "<!doctype html><html><head><title>ok</title></head>"
    "<body><p>noop</p></body></html>"
)

_BLOCKED_HTML_PATTERNS = [
    "<!doctype html><html><body>Please enable JavaScript to continue.</body></html>",
    "<!doctype html><html><body>Checking your browser before accessing example.com.</body></html>",
    "<!doctype html><html><body>Access Denied</body></html>",
    "<!doctype html><html><body><title>Just a moment...</title></body></html>",
]


# ── Layer 1: registry sanity ──────────────────────────────────────────────


class TestScraperRegistryContract:
    """Every stable+search scraper can be imported and instantiated."""

    def test_search_capable_slugs_nonempty(self):
        assert _search_capable_slugs(), "registry produced zero search-capable slugs"

    @pytest.mark.parametrize("slug", _search_capable_slugs())
    def test_scraper_class_importable(self, slug):
        cls = _import_scraper_class(slug)
        assert cls.__name__ == SCRAPERS[slug].class_name
        from newswatch.scrapers.basescraper import BaseScraper
        assert issubclass(cls, BaseScraper)

    @pytest.mark.parametrize("slug", _search_capable_slugs())
    def test_scraper_instantiable_with_registry_keyword(self, slug):
        cls = _import_scraper_class(slug)
        s = cls(keywords=SCRAPERS[slug].smoke_keyword)
        assert s.keywords == [SCRAPERS[slug].smoke_keyword]
        assert isinstance(getattr(s, "base_url", None), str) and s.base_url


# ── Layer 2: parse contract (offline via aioresponses) ────────────────────


class TestScraperParseContract:
    """build_search_url to fetch to parse_article_links round-trip with mocked HTTP."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("slug", _search_capable_slugs())
    async def test_search_handles_empty_response_without_raising(self, slug):
        """The full search pipeline runs against mocked HTTP. Real
        build_search_url is exercised so adapter-specific state mutation
        (e.g. gatra._current_keyword) is set the way production sets it;
        aioresponses intercepts the resulting URL via a regex match.

        Browser-required search scrapers are intentionally skipped because
        their ``async with`` entry launches Playwright, which aioresponses
        cannot intercept and which is not installed in the unit CI.
        """
        entry = SCRAPERS[slug]
        if entry.browser_required:
            pytest.skip("browser_required search scraper uses Playwright; not offline")

        cls = _import_scraper_class(slug)
        s = cls(
            keywords=entry.smoke_keyword,
            start_date=datetime.now() - timedelta(days=7),
            queue_=asyncio.Queue(),
        )
        async with s:
            with aioresponses() as m:
                m.get(re.compile(r".*"), body=_PASSTHROUGH_HTML, status=200, repeat=True)
                m.post(re.compile(r".*"), body=_PASSTHROUGH_HTML, status=200, repeat=True)
                await s.fetch_search_results(entry.smoke_keyword)
            assert s._articles_collected == 0


# ── Layer 2b: latest-mode parse contract (offline via aioresponses) ───────


class TestScraperLatestParseContract:
    """build_latest_url to fetch_latest_results round-trip with mocked HTTP.

    Browser-required latest scrapers are intentionally skipped here. Their
    latest paths launch Playwright, and aioresponses cannot intercept CDP
    browser traffic. They are still covered by registry invariants and by
    the network-marked live suite.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("slug", _latest_capable_slugs())
    async def test_latest_handles_empty_response_without_raising(self, slug):
        """Latest-mode empty-body contract: never raise, zero articles."""
        entry = SCRAPERS[slug]
        if entry.browser_required:
            pytest.skip("browser_required latest scraper uses Playwright; not offline")

        cls = _import_scraper_class(slug)
        s = cls(
            keywords=entry.smoke_keyword,
            start_date=datetime.now() - timedelta(days=7),
            queue_=asyncio.Queue(),
        )
        async with s:
            with aioresponses() as m:
                m.get(re.compile(r".*"), body=_PASSTHROUGH_HTML, status=200, repeat=True)
                m.post(re.compile(r".*"), body=_PASSTHROUGH_HTML, status=200, repeat=True)
                await s.fetch_latest_results()
            assert s._articles_collected == 0


# ── Layer 3: block detection ─────────────────────────────────────────────


class TestScraperBlockDetection:
    """``_looks_blocked`` must keep flagging the canonical WAF/CDN markers."""

    @pytest.mark.parametrize("body", _BLOCKED_HTML_PATTERNS)
    def test_blocked_body_detected_by_looks_blocked(self, body):
        assert _looks_blocked(body), f"expected '{body[:40]}' to be flagged blocked"

    def test_passthrough_body_not_flagged(self):
        assert not _looks_blocked(_PASSTHROUGH_HTML)


# ── Concurrency and smoke-keyword invariants ──────────────────────────────


class TestScraperInvariants:
    """Defensive: every registered scraper reports sane concurrency and
    a non-empty smoke_keyword (the keyword the redev refresh ensured)."""

    @pytest.mark.parametrize("slug", _search_capable_slugs())
    def test_concurrency_positive(self, slug):
        entry = SCRAPERS[slug]
        assert entry.concurrency >= 1, f"{slug} has concurrency={entry.concurrency}"

    @pytest.mark.parametrize("slug", _search_capable_slugs())
    def test_smoke_keyword_nonempty(self, slug):
        entry = SCRAPERS[slug]
        assert entry.smoke_keyword and entry.smoke_keyword.strip(), (
            f"{slug} has empty smoke_keyword"
        )


# ── Latest-mode invariants (mirrors above for supports_latest slugs) ──────


class TestScraperLatestInvariants:
    """Same defensive invariants as ``TestScraperInvariants`` but for the
    superset of stable scrapers that support ``method="latest"``. The
    three latest-only slugs (aljazeera, balipost, cnaindonesia) live
    exclusively in this layer; they never reach the search-side tests."""

    @pytest.mark.parametrize("slug", _latest_capable_slugs())
    def test_concurrency_positive_latest(self, slug):
        entry = SCRAPERS[slug]
        assert entry.concurrency >= 1, f"{slug} has concurrency={entry.concurrency}"

    @pytest.mark.parametrize("slug", _latest_capable_slugs())
    def test_smoke_keyword_nonempty_latest(self, slug):
        entry = SCRAPERS[slug]
        assert entry.smoke_keyword and entry.smoke_keyword.strip(), (
            f"{slug} has empty smoke_keyword"
        )
