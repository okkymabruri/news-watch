"""Deterministic scraper capability contracts."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from urllib.parse import quote

import pytest

from newswatch.registry import SCRAPERS, get_stable_slugs
from newswatch.scrapers.basescraper import BaseScraper


class FetchSpy:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def __call__(self, url: str, *args, **kwargs) -> str:
        self.urls.append(url)
        return url


def scraper_class(slug: str) -> type[BaseScraper]:
    entry = SCRAPERS[slug]
    module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
    return getattr(module, entry.class_name)


def capable_pairs(mode: str) -> list[tuple[str, type[BaseScraper]]]:
    field = f"supports_{mode}"
    return [
        (slug, scraper_class(slug))
        for slug in sorted(get_stable_slugs())
        if getattr(SCRAPERS[slug], field)
    ]


def generic_pairs(mode: str) -> list[tuple[str, type[BaseScraper]]]:
    base_fetch = getattr(BaseScraper, f"fetch_{mode}_results")
    return [
        (slug, adapter)
        for slug, adapter in capable_pairs(mode)
        if getattr(adapter, f"fetch_{mode}_results") is base_fetch
    ]


def custom_pairs(mode: str) -> list[tuple[str, type[BaseScraper]]]:
    base_fetch = getattr(BaseScraper, f"fetch_{mode}_results")
    return [
        (slug, adapter)
        for slug, adapter in capable_pairs(mode)
        if getattr(adapter, f"fetch_{mode}_results") is not base_fetch
    ]


_GENERIC_SEARCH = generic_pairs("search")
_CUSTOM_SEARCH = custom_pairs("search")
_GENERIC_LATEST = generic_pairs("latest")
_CUSTOM_LATEST = custom_pairs("latest")


@pytest.mark.parametrize(
    "slug,adapter", _GENERIC_SEARCH, ids=[slug for slug, _ in _GENERIC_SEARCH]
)
def test_generic_search_capability_has_build_and_parse_hooks(slug, adapter):
    assert adapter.build_search_url is not BaseScraper.build_search_url, slug
    assert adapter.parse_article_links is not BaseScraper.parse_article_links, slug


@pytest.mark.parametrize(
    "slug,adapter", _CUSTOM_SEARCH, ids=[slug for slug, _ in _CUSTOM_SEARCH]
)
def test_custom_search_capability_has_async_workflow(slug, adapter):
    assert adapter.fetch_search_results is not BaseScraper.fetch_search_results, slug
    assert inspect.iscoroutinefunction(adapter.fetch_search_results), slug


@pytest.mark.parametrize(
    "slug,adapter", _GENERIC_LATEST, ids=[slug for slug, _ in _GENERIC_LATEST]
)
def test_generic_latest_capability_has_build_and_parse_hooks(slug, adapter):
    assert adapter.build_latest_url is not BaseScraper.build_latest_url, slug
    assert adapter.parse_latest_article_links is not BaseScraper.parse_latest_article_links, slug


@pytest.mark.parametrize(
    "slug,adapter", _CUSTOM_LATEST, ids=[slug for slug, _ in _CUSTOM_LATEST]
)
def test_custom_latest_capability_has_async_workflow(slug, adapter):
    assert adapter.fetch_latest_results is not BaseScraper.fetch_latest_results, slug
    assert inspect.iscoroutinefunction(adapter.fetch_latest_results), slug


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "keyword", ["politik", "politik luar negeri", "ihsg/market", "ekonomi & bisnis"]
)
async def test_cna_topic_search_quotes_keyword(keyword):
    scraper = scraper_class("cnaindonesia")(keywords=keyword, queue_=asyncio.Queue())
    spy = FetchSpy()
    scraper.fetch = spy

    await scraper.build_search_url(keyword, 1)

    assert spy.urls == [f"https://www.cna.id/topic/{quote(keyword, safe='')}"]


@pytest.mark.asyncio
async def test_cna_topic_search_stops_after_first_page():
    scraper = scraper_class("cnaindonesia")(keywords="politik", queue_=asyncio.Queue())
    spy = FetchSpy()
    scraper.fetch = spy

    assert await scraper.build_search_url("politik", 2) is None
    assert spy.urls == []


def test_cna_topic_parser_keeps_only_articles():
    scraper = scraper_class("cnaindonesia")(keywords="politik", queue_=asyncio.Queue())
    html = """
    <html><body>
      <a href="/topic/politik">Topic</a>
      <a href="/indonesia">Category</a>
      <a href="/indonesia/pemilu-resmi-digelar-12345">Article</a>
      <a href="https://www.cna.id/asia/ktt-asean-67890">Asia article</a>
    </body></html>
    """

    assert scraper.parse_article_links(html) == {
        "https://www.cna.id/indonesia/pemilu-resmi-digelar-12345",
        "https://www.cna.id/asia/ktt-asean-67890",
    }
    no_articles = "<html><a href='/topic/politik'>Topic</a></html>"
    assert scraper.parse_article_links(no_articles) is None


def test_bali_search_shell_has_no_static_articles():
    scraper = scraper_class("balipost")(keywords="ekonomi", queue_=asyncio.Queue())
    html = """
    <html><body>
      <div class="gcse-searchresults-only"></div>
      <noscript>Silahkan Enable JavaScript Pada Browser Anda!</noscript>
    </body></html>
    """

    assert scraper.parse_article_links(html) is None
    assert SCRAPERS["balipost"].supports_search is False


def test_bali_latest_parser_keeps_article_links():
    scraper = scraper_class("balipost")(keywords="ekonomi", queue_=asyncio.Queue())
    html = """
    <html><body>
      <a href="/news/nasional/">Category</a>
      <a href="/news/2026/05/15/56789/Pariwisata-Bali-Meningkat.html">Article</a>
    </body></html>
    """

    assert scraper.parse_latest_article_links(html) == {
        "https://www.balipost.com/news/2026/05/15/56789/Pariwisata-Bali-Meningkat.html"
    }


def test_registry_matches_verified_cna_bali_capabilities():
    assert SCRAPERS["cnaindonesia"].supports_search is True
    assert SCRAPERS["cnaindonesia"].supports_latest is True
    assert SCRAPERS["balipost"].supports_search is False
    assert SCRAPERS["balipost"].supports_latest is True
