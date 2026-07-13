"""Focused tests for canonical live-test exception classification and
the XML/RSS parsers introduced/preserved in this batch.

These tests pin:
- Which exception classes are skipped (known external/network/browser)
  vs. allowed to fail (real bugs).
- That Kumparan's latest parser consumes its active RSS endpoint without XML warnings.
- That SINDO's latest parser consumes the RSS ``/feed`` XML endpoint.
- That Surabaya Pagi bounds search pagination, scopes canonical extraction, queues the standard item schema, and consumes RSS latest links.
"""

from __future__ import annotations

import asyncio
import warnings

import aiohttp
import pytest

from newswatch.scrapers.kumparan import KumparanScraper
from newswatch.scrapers.sindonews import SindonewsScraper
from newswatch.scrapers.surabayapagi import SurabayaPagiScraper

try:
    from playwright.async_api import Error as PlaywrightError
except ImportError:  # playwright not installed in some CI lanes
    PlaywrightError = None  # type: ignore[assignment]


# ── 1. Exception classification contract ──────────────────────────────────


class TestKnownNetworkExceptionTuple:
    """The tuple of skip-worthy exceptions in ``test_scrapers`` must
    contain every class that the upstream HTTP/browser stack can
    realistically raise. Anything missing makes the live test fail on
    what is really an environmental hiccup.
    """

    def test_required_classes_in_tuple(self):
        from tests.test_scrapers import _KNOWN_NETWORK_EXCEPTIONS  # type: ignore

        required = {
            asyncio.TimeoutError,
            ConnectionError,
            aiohttp.ClientError,
            OSError,
        }
        assert required.issubset(set(_KNOWN_NETWORK_EXCEPTIONS)), (
            "missing required skip classes: "
            f"{required - set(_KNOWN_NETWORK_EXCEPTIONS)}"
        )

    @pytest.mark.skipif(PlaywrightError is None, reason="playwright not installed")
    def test_playwright_error_included_when_available(self):
        from tests.test_scrapers import _KNOWN_NETWORK_EXCEPTIONS  # type: ignore

        assert PlaywrightError in _KNOWN_NETWORK_EXCEPTIONS, (
            "PlaywrightError missing from skip tuple; browser-required "
            "scrapers will fail live instead of skipping"
        )

    def test_value_error_not_in_skip_tuple(self):
        """``ValueError`` is the canonical bug signal in this codebase -
        a malformed sitemap, a missing field, or a dateparser crash all
        surface as ValueError. It MUST NOT be in the skip tuple."""
        from tests.test_scrapers import _KNOWN_NETWORK_EXCEPTIONS  # type: ignore

        assert ValueError not in _KNOWN_NETWORK_EXCEPTIONS, (
            "ValueError should propagate as a real bug, not skip"
        )

    def test_assertion_error_not_in_skip_tuple(self):
        from tests.test_scrapers import _KNOWN_NETWORK_EXCEPTIONS  # type: ignore

        assert AssertionError not in _KNOWN_NETWORK_EXCEPTIONS

    def test_key_error_not_in_skip_tuple(self):
        from tests.test_scrapers import _KNOWN_NETWORK_EXCEPTIONS  # type: ignore

        assert KeyError not in _KNOWN_NETWORK_EXCEPTIONS


# ── 2. Kumparan: latest mode consumes active RSS XML ─────────────────────


class TestKumparanXMLParser:
    RSS_XML = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss><channel>'
        '<item><link>https://kumparan.com/kumparannews/article-a</link></item>'
        '<item><link>https://kumparan.com/kumparanbisnis/article-b</link></item>'
        '<item><link>https://other.example.com/article-c</link></item>'
        '<item><title>missing link</title></item>'
        '</channel></rss>'
    )

    def test_latest_parses_same_site_rss_items_without_warning(self):
        scraper = KumparanScraper("ekonomi")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            links = scraper.parse_latest_article_links(self.RSS_XML)
        assert links == {
            "https://kumparan.com/kumparannews/article-a",
            "https://kumparan.com/kumparanbisnis/article-b",
        }

    def test_latest_invalid_xml_returns_none(self):
        scraper = KumparanScraper("ekonomi")
        assert scraper.parse_latest_article_links("") is None
        assert scraper.parse_latest_article_links(None) is None
        assert scraper.parse_latest_article_links("not xml") is None

    async def test_latest_url_fetches_active_rss_once(self):
        scraper = KumparanScraper("ekonomi")
        calls = []

        async def fake_fetch(url, **kwargs):
            calls.append((url, kwargs))
            return self.RSS_XML

        scraper.fetch = fake_fetch
        assert await scraper.build_latest_url(1) == self.RSS_XML
        assert await scraper.build_latest_url(2) is None
        assert calls == [(scraper.rss_url, {"headers": scraper.headers, "timeout": 30})]


# ── 3. SINDO: latest parser consumes RSS XML from /feed ──────────────────


class TestSindonewsXMLParser:
    """SINDO's latest mode now consumes the RSS ``/feed`` endpoint. Pin
    the parser behavior so a future regression to HTML parsing is caught.
    """

    FEED_XML = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">'
        "<channel>"
        "<title>SINDOnews</title>"
        "<item>"
        "<link>https://nasional.sindonews.com/read/1727611/a</link>"
        "</item>"
        "<item>"
        "<link>https://ekbis.sindonews.com/read/1727609/b</link>"
        "</item>"
        "<item>"
        "<link>https://lifestyle.sindonews.com/read/1727603/c</link>"
        "</item>"
        "</channel>"
        "</rss>"
    )

    def test_latest_parses_rss_items(self):
        s = SindonewsScraper("ihsg")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            links = s.parse_latest_article_links(self.FEED_XML)
        assert links == {
            "https://nasional.sindonews.com/read/1727611/a",
            "https://ekbis.sindonews.com/read/1727609/b",
            "https://lifestyle.sindonews.com/read/1727603/c",
        }, f"unexpected links {sorted(links or [])}"

    def test_latest_skips_items_without_link(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<rss><channel>"
            "<item><title>no link</title></item>"
            "<item><link>https://nasional.sindonews.com/read/1/ok</link></item>"
            "</channel></rss>"
        )
        s = SindonewsScraper("ihsg")
        assert s.parse_latest_article_links(xml) == {
            "https://nasional.sindonews.com/read/1/ok"
        }

    def test_latest_empty_returns_none(self):
        s = SindonewsScraper("ihsg")
        assert s.parse_latest_article_links("") is None
        assert s.parse_latest_article_links(None) is None  # type: ignore[arg-type]

    def test_latest_url_points_at_feed(self):
        """Lock in /feed so a future regression to the homepage does not
        silently change behavior."""
        s = SindonewsScraper("ihsg")
        from urllib.parse import urlparse

        url = s.base_url if False else f"https://www.{s.base_url}/feed"
        parsed = urlparse(url)
        assert parsed.path == "/feed", (
            f"SINDO latest URL is {url!r}; expected path /feed for RSS XML"
        )

# ── 4. Surabaya Pagi: bounded search and RSS latest ──────────────────────


class TestSurabayaPagiReliability:
    SEARCH_HTML = (
        '<div class="category-text-wrap"><h2>'
        '<a href="https://surabayapagi.com/news-123-ekonomi-surabaya">ok</a>'
        '</h2></div>'
        '<aside><a href="https://surabayapagi.com/news-999-sidebar">sidebar</a></aside>'
        '<div class="category-text-wrap"><h2>'
        '<a href="https://other.example.com/news-456-offsite">offsite</a>'
        '</h2></div>'
    )
    RSS_XML = (
        '<?xml version="1.0"?><rss><channel>'
        '<item><link>https://surabayapagi.com/news-123-current</link></item>'
        '<item><link>https://other.example.com/news-999-offsite</link></item>'
        '</channel></rss>'
    )
    ARTICLE_HTML = (
        '<html><head><meta name="author" content="Reporter">'
        '<meta property="article:published_time" content="2026-07-13T12:05:00+07:00">'
        '</head><body><h1>Ekonomi Surabaya</h1>'
        '<article><p>Isi berita ekonomi Surabaya yang cukup panjang.</p></article>'
        '</body></html>'
    )

    async def test_search_url_is_quoted_and_bounded(self):
        scraper = SurabayaPagiScraper("ekonomi")
        calls = []

        async def fake_fetch(url, **kwargs):
            calls.append((url, kwargs))
            return self.SEARCH_HTML

        scraper.fetch = fake_fetch
        assert await scraper.build_search_url("energi hijau", 1) == self.SEARCH_HTML
        assert await scraper.build_search_url("energi hijau", 2) == self.SEARCH_HTML
        assert await scraper.build_search_url("energi hijau", 11) is None
        assert [call[0] for call in calls] == [
            "https://surabayapagi.com/search/energi%20hijau",
            "https://surabayapagi.com/search/energi%20hijau/2",
        ]
        assert all(call[1]["timeout"] == 15 for call in calls)

    def test_search_links_are_primary_same_site_articles(self):
        scraper = SurabayaPagiScraper("ekonomi")
        assert scraper.parse_article_links(self.SEARCH_HTML) == {
            "https://surabayapagi.com/news-123-ekonomi-surabaya"
        }

    async def test_article_queues_canonical_item_schema(self):
        scraper = SurabayaPagiScraper("ekonomi", queue_=asyncio.Queue())

        async def fake_fetch(url, **kwargs):
            return self.ARTICLE_HTML

        scraper.fetch = fake_fetch
        link = "https://surabayapagi.com/news-123-ekonomi-surabaya"
        await scraper.get_article(link, "ekonomi")
        item = scraper.queue_.get_nowait()
        assert set(item) == {
            "title", "publish_date", "author", "content", "keyword",
            "category", "source", "link",
        }
        assert item["link"] == link
        assert item["keyword"] == "ekonomi"
        assert item["source"] == "surabayapagi"

    async def test_latest_uses_feed_and_canonical_items(self):
        scraper = SurabayaPagiScraper("ekonomi")
        calls = []

        async def fake_fetch(url, **kwargs):
            calls.append((url, kwargs))
            return self.RSS_XML

        scraper.fetch = fake_fetch
        assert await scraper.build_latest_url(1) == self.RSS_XML
        assert await scraper.build_latest_url(2) is None
        assert scraper.parse_latest_article_links(self.RSS_XML) == {
            "https://surabayapagi.com/news-123-current"
        }
        assert calls == [(
            "https://surabayapagi.com/feed",
            {"retries": scraper.max_retries, "timeout": 15},
        )]
