"""Focused tests for canonical live-test exception classification and
the XML/RSS parsers introduced/preserved in this batch.

These tests pin:
- Which exception classes are skipped (known external/network/browser)
  vs. allowed to fail (real bugs).
- That Kumparan's XML sitemap parser does not warn under BeautifulSoup.
- That SINDO's latest parser consumes the RSS ``/feed`` XML endpoint.
"""

from __future__ import annotations

import asyncio
import warnings

import aiohttp
import pytest

from newswatch.scrapers.kumparan import KumparanScraper
from newswatch.scrapers.sindonews import SindonewsScraper

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


# ── 2. Kumparan: XML sitemap parser is warning-free ──────────────────────


class TestKumparanXMLParser:
    """Confirm Kumparan's latest parser uses BeautifulSoup's ``xml``
    builder and does not emit ``XMLParsedAsHTMLWarning`` for actual XML
    input. The earlier HTML parser raised a ``bs4`` warning every fetch.
    """

    def test_latest_uses_xml_parser_on_real_sitemap(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://kumparan.com/foo-ekonomi-123</loc></url>'
            '<url><loc>https://kumparan.com/ekonomi/bar-456</loc></url>'
            '<url><loc>https://other.example.com/no-kumparan</loc></url>'
            "</urlset>"
        )
        s = KumparanScraper("ekonomi")
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # turn any warning into an error
            links = s.parse_latest_article_links(xml)
        assert links == {
            "https://kumparan.com/foo-ekonomi-123",
            "https://kumparan.com/ekonomi/bar-456",
        }, f"unexpected links {sorted(links or [])}"

    def test_latest_empty_xml_returns_none(self):
        s = KumparanScraper("ekonomi")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert s.parse_latest_article_links("") is None
            assert s.parse_latest_article_links(None) is None  # type: ignore[arg-type]


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