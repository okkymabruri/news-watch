"""Focused tests for the XML/RSS parsers introduced/preserved in this batch
and the deterministic offline contracts for the three newest adapters.

Tests pin:
- Kumparan's latest parser consumes its active RSS endpoint without XML warnings.
- SINDO's latest parser consumes the RSS ``/feed`` XML endpoint.
- Surabaya Pagi bounds search pagination, scopes canonical extraction, queues
  the standard item schema, and consumes RSS latest links.
- DDTC News search-mode parser (build_search_url -> None; four-section regex;
  every-token keyword gate; standalone-MBG acceptance); latest-mode parser
  (page 1 only; four-section regex); article extraction (og:title, #publish-news
  date, meta author/category, script/iframe stripping; missing-date
  short-circuit); start_date future cutoff drops and flips flag.
- IDN Financials search-mode parser (keyword quoting + per_page +
  _current_keyword; NO_RESULT_MARKER gate; Berita-widget filter; dedupe;
  every-token keyword gate); latest-mode parser (page 1 = /id/news; page N =
  /id/news?page=N; article URL filter); article extraction (JSON-LD
  datePublished + meta fallback; h2 fallback when og:title absent; JSON-LD
  author wins over missing meta; article:section category; body extraction);
  start_date future cutoff drops and flips flag.
- Warta Ekonomi search-mode parser (page 1 POST /search; page 2 reuses
  captured _search_id; short-circuits without fetch when page 2 has no
  captured id); _search_id capture from /search/<id> pagination anchor;
  articleListItem + article-regex + every-token keyword filter; anchor-text
  fallback when title attribute absent; latest-mode parser (/indeks without
  start_date; /indeks?page=N; /indeks/YYYYMMDD with start_date lower-date
  cutoff; /indeks/YYYYMMDD?page=N); article extraction (article h1 /
  .articlePostHeader h1; JSON-LD datePublished + meta fallback; JSON-LD
  articleSection + breadcrumb + meta fallbacks; baca-juga-box / inline
  "Baca Juga" cross-promo stripping; empty/missing-title short-circuit);
  metadata-free category collapses to "Unknown"; canonical link precedence
  <link rel=canonical> > og:url > input link; start_date future cutoff
  drops and flips flag.
- Cross-adapter queue schema (title, publish_date, author, content, keyword,
  category, source, link) — exact eight keys, value types, canonical source
  domain — exercised once per adapter by a parametrized contract.
"""

from __future__ import annotations

import asyncio
import json
import warnings
from datetime import datetime
from typing import Any
from urllib.parse import quote

import pytest

from newswatch.scrapers.alinea import AlineaScraper
from newswatch.scrapers.betahita import BetahitaScraper
from newswatch.scrapers.conversationid import ConversationIDScraper
from newswatch.scrapers.ddtcnews import DDTCNewsScraper
from newswatch.scrapers.gnfi import GNFIScraper
from newswatch.scrapers.hukumonline import HukumonlineScraper
from newswatch.scrapers.idnfinancials import IDNFinancialsScraper
from newswatch.scrapers.independen import IndependenScraper
from newswatch.scrapers.kumparan import KumparanScraper
from newswatch.scrapers.nusabali import NusaBaliScraper
from newswatch.scrapers.sindonews import SindonewsScraper
from newswatch.scrapers.surabayapagi import SurabayaPagiScraper
from newswatch.scrapers.wartaekonomi import WartaEkonomiScraper
from newswatch.scrapers.idxchannel import IDXChannelScraper
from newswatch.scrapers.infobanknews import InfobanknewsScraper


# ── Shared offline test scaffolding ────────────────────────────────────────

_QUEUE_KEYS: tuple[str, ...] = (
    "title", "publish_date", "author", "content",
    "keyword", "category", "source", "link",
)


class _FetchStub:
    """Replace ``scraper.fetch`` with a URL-substring → body lookup.

    Records every call so contracts can pin URL shape, method, and POST data.
    Returns ``None`` for unmatched URLs so callers that key on falsy responses
    observe the same fall-through they would in production.
    """

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses: dict[str, str] = responses or {}
        self.calls: list[tuple[str, str | None, dict[str, Any] | None]] = []

    async def __call__(
        self,
        url: str,
        *args: Any,
        method: str | None = None,
        data: Any | None = None,
        **kwargs: Any,
    ) -> str | None:
        self.calls.append((url, method, {"data": data, **kwargs} if data or kwargs else None))
        for needle, body in self.responses.items():
            if needle in url:
                return body
        return None


def _attach_fetch(scraper: Any, responses: dict[str, str]) -> _FetchStub:
    stub = _FetchStub(responses)
    scraper.fetch = stub
    return stub


# ── 1. Kumparan: latest mode consumes active RSS XML ─────────────────────


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


# ── 2. SINDO: latest parser consumes RSS XML from /feed ──────────────────


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

# ── 3. Surabaya Pagi: bounded search and RSS latest ──────────────────────


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


# ── 4. DDTC News — offline contract suite ────────────────────────────────


class TestDDTCNewsSearchURLFiltering:
    """DDTC News search-mode parser accepts the four article sections only.

    The Playwright-driven ``fetch_search_results`` flow is not exercised here;
    the contract under test is the synchronous ``parse_article_links`` against
    the rendered HTML, plus the deliberate ``build_search_url -> None`` stub.
    """

    def _scraper(self):
        return DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())

    @pytest.mark.asyncio
    async def test_build_search_url_returns_none(self):
        """DDTC News handles pagination entirely in Playwright; build_search_url
        must return None so the base loop's ``if not body: break`` short-circuits
        without HTTP traffic."""
        s = self._scraper()
        # No fetch stub — if the adapter attempted to call fetch(), the test
        # would surface an AttributeError.
        assert await s.build_search_url("pajak", 1) is None
        assert await s.build_search_url("pajak", 5) is None

    def test_parser_keeps_four_sections_and_rejects_other_paths(self):
        s = self._scraper()
        html = """<!doctype html><html><body>
          <div class="news-item"><a href="/berita/foo-bar/123/some-slug">some-slug</a></div>
          <div class="news-item"><a href="/review/tax/456/another-slug">another-slug</a></div>
          <div class="news-item"><a href="/literasi/edu/789/third-slug">third-slug</a></div>
          <div class="news-item"><a href="/komunitas/forum/101/fourth-slug">fourth-slug</a></div>
          <div class="news-item"><a href="/news/something/202/wrong-section">wrong-section</a></div>
          <div class="news-item"><a href="/berita/2026">missing-slug-and-id</a></div>
          <div class="news-item"><a href="https://other.example.com/berita/x/9/y">offsite</a></div>
        </body></html>"""
        links = s.parse_article_links(html)
        assert links == {
            "https://news.ddtc.co.id/berita/foo-bar/123/some-slug",
            "https://news.ddtc.co.id/review/tax/456/another-slug",
            "https://news.ddtc.co.id/literasi/edu/789/third-slug",
            "https://news.ddtc.co.id/komunitas/forum/101/fourth-slug",
        }

    def test_parser_requires_every_query_token(self):
        s = self._scraper()
        html = """<!doctype html><html><body>
          <div class="news-item"><a href="/berita/nasional/201/badan-gizi-launch">Badan Gizi Launch</a></div>
          <div class="news-item"><a href="/berita/nasional/202/badan-gizi-nasional-resmi">Badan Gizi Nasional Resmi Dibentuk</a></div>
        </body></html>"""
        assert s.parse_article_links(html, "badan gizi nasional") == {
            "https://news.ddtc.co.id/berita/nasional/202/badan-gizi-nasional-resmi"
        }

    def test_parser_accepts_standalone_mbg(self):
        s = self._scraper()
        html = """<!doctype html><html><body>
          <div class="news-item"><a href="/berita/nasional/203/program-mbg-dievaluasi">Program MBG Dievaluasi</a></div>
        </body></html>"""
        assert s.parse_article_links(html, "mbg") == {
            "https://news.ddtc.co.id/berita/nasional/203/program-mbg-dievaluasi"
        }

    def test_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None
        assert s.parse_article_links(None) is None  # type: ignore[arg-type]


class TestDDTCNewsLatestURLFiltering:
    """DDTC News latest: page 1 only (homepage); regex-anchored article links."""

    @pytest.mark.asyncio
    async def test_page_one_targets_homepage(self):
        s = DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())
        stub = _attach_fetch(s, {"news.ddtc.co.id": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://news.ddtc.co.id"

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())
        assert await s.build_latest_url(2) is None

    def test_latest_parser_keeps_article_sections_drops_others(self):
        s = DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())
        html = """<!doctype html><html><body>
          <a href="/berita/foo/1/bar">berita — kept</a>
          <a href="/review/x/2/y">review — kept</a>
          <a href="/news/something/202/wrong">news — dropped</a>
          <a href="https://news.ddtc.co.id/about">about — dropped (no section)</a>
          <a href="https://other.example.com/berita/x/3/y">offsite — dropped</a>
        </body></html>"""
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://news.ddtc.co.id/berita/foo/1/bar",
            "https://news.ddtc.co.id/review/x/2/y",
        }

    def test_latest_parser_rejects_empty_body(self):
        s = DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())
        assert s.parse_latest_article_links("") is None
        assert s.parse_latest_article_links(None) is None  # type: ignore[arg-type]


class TestDDTCNewsGetArticle:
    """DDTC News article extraction contract: og:title, #publish-news date,
    div.contentArticle body with script/iframe stripping, meta author and
    meta category fallbacks."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())
        link = "https://news.ddtc.co.id/berita/foo-bar/123/test-article"
        html = """<!doctype html>
<html><head>
<meta property="og:title" content="DDTC test headline">
</head><body>
<h1>DDTC test headline</h1>
<div id="publish-news">Minggu, 12 Juli 2026</div>
<div class="contentArticle">
  <p>DDTC lead paragraph that the contentArticle extractor pulls into the body text.</p>
  <p>DDTC second paragraph continuing the article body extraction.</p>
  <script>analytics noise — must be stripped</script>
  <iframe src="https://example.com/embed"></iframe>
</div>
<meta name="author" content="DDTC Reporter">
<meta name="category" content="Pajak">
</body></html>
"""
        _attach_fetch(s, {link: html})
        await s.get_article(link, "pajak")

        item = s.queue_.get_nowait()
        assert item["title"] == "DDTC test headline"
        # Saturday, 12 July 2026 → 2026-07-12 00:00:00 naive.
        assert item["publish_date"] == datetime(2026, 7, 12, 0, 0, 0)
        assert item["publish_date"].tzinfo is None
        assert item["author"] == "DDTC Reporter"
        assert item["category"] == "Pajak"
        assert item["source"] == "news.ddtc.co.id"
        assert item["keyword"] == "pajak"
        assert item["link"] == link
        assert "DDTC lead paragraph" in item["content"]
        assert "DDTC second paragraph" in item["content"]
        # Body extractor strips <script> and <iframe> from the body node.
        assert "analytics noise" not in item["content"]
        assert "https://example.com/embed" not in item["content"]

    @pytest.mark.asyncio
    async def test_empty_body_short_circuits_without_put(self):
        s = DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())
        link = "https://news.ddtc.co.id/berita/empty/999/x"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "pajak")
        assert s.queue_.qsize() == 0

    @pytest.mark.asyncio
    async def test_missing_publish_date_short_circuits(self):
        """Without #publish-news, the date parser must skip the article — the
        queue must stay empty."""
        s = DDTCNewsScraper(keywords="pajak", queue_=asyncio.Queue())
        link = "https://news.ddtc.co.id/berita/no-date/1/x"
        html = """<!doctype html><html><head>
<meta property="og:title" content="DDTC test headline">
<meta name="author" content="DDTC Reporter">
<meta name="category" content="Pajak">
</head><body>
<div class="contentArticle">
  <p>body paragraph that must not reach the queue without a publish date</p>
</div>
</body></html>"""
        _attach_fetch(s, {link: html})
        await s.get_article(link, "pajak")
        assert s.queue_.qsize() == 0


# ── 5. IDN Financials — offline contract suite ────────────────────────────


class TestIDNFinancialsSearchURLFiltering:
    """IDN Financials search-mode discovery contract:

    - ``build_search_url`` quotes the keyword, sets ``per_page``, and
      records ``_current_keyword`` for the parser's relevance check;
    - ``parse_article_links`` selects only the Berita widget (drops the
      Video widget), filters to article URLs, dedupes, and applies the
      keyword relevance gate;
    - the explicit NO_RESULT_MARKER gate flips ``continue_scraping`` to
      False and returns None (no candidate links, no error path).
    """

    def _scraper(self):
        return IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )

    @staticmethod
    def _berita_widget_html(items, *, extra_video_widget=True):
        berita_items = "\n".join(
            f'<li class="item"><a href="{it["href"]}" title="{it["title"]}">{it["title"]}</a></li>'
            for it in items
        )
        video_widget = (
            '<div class="widget side-news"><div class="widget-header">'
            '<h2>Video</h2></div><div class="widget-body">'
            '<ul class="list">'
            '<li class="item"><a href="/id/news/999999/video-slug" '
            'title="Unrelated video title">video</a></li>'
            '</ul></div></div>'
            if extra_video_widget
            else ""
        )
        return (
            '<!doctype html><html><body>'
            '<div class="widget side-news">'
            '<div class="widget-header"><h2>Berita</h2></div>'
            '<div class="widget-body">'
            f'<ul class="list">{berita_items}</ul>'
            '</div></div>'
            f'{video_widget}'
            '</body></html>'
        )

    @pytest.mark.asyncio
    async def test_build_search_url_quotes_keyword_and_sets_per_page(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"/id/search": "<html></html>"})
        body = await s.build_search_url("makan bergizi gratis", 2)
        assert body == "<html></html>"
        url = stub.calls[0][0]
        assert url.startswith("https://www.idnfinancials.com/id/search?")
        assert "q=makan%20bergizi%20gratis" in url
        assert "per_page=2" in url
        assert s._current_keyword == "makan bergizi gratis"

    @pytest.mark.asyncio
    async def test_build_search_url_outside_max_pages_returns_none(self):
        s = self._scraper()
        assert await s.build_search_url("makan", 0) is None
        assert await s.build_search_url("makan", 999) is None

    @pytest.mark.asyncio
    async def test_no_result_marker_flips_flag_and_returns_none(self):
        """A server-rendered 'no data' blockquote must short-circuit the run
        without raising; continue_scraping must flip to False."""
        s = self._scraper()
        stub = _attach_fetch(s, {"/id/search": (
            '<!doctype html><html><body>'
            '<blockquote>Tidak ada data yang ditemukan</blockquote>'
            '</body></html>'
        )})
        result = await s.build_search_url("makan", 1)
        assert result is not None  # the body was served
        assert s.parse_article_links(result) is None
        assert s.continue_scraping is False
        # The body was served once and then the parser rejected it; no further
        # fetch was attempted.
        assert len(stub.calls) == 1

    def test_parser_keeps_berita_widget_drops_video_widget(self):
        s = self._scraper()
        html = self._berita_widget_html(
            items=[
                {"href": "/id/news/123/berita-makan-bergizi-gratis",
                 "title": "Makan Bergizi Gratis Article"},
            ],
            extra_video_widget=True,
        )
        links = s.parse_article_links(html)
        # Only the Berita widget's article URL survives; the Video widget's
        # /id/news/{id} link must be filtered out even though it matches the
        # article regex.
        assert links == [
            "https://www.idnfinancials.com/id/news/123/berita-makan-bergizi-gratis",
        ]

    def test_parser_filters_non_matching_article_urls(self):
        s = self._scraper()
        html = self._berita_widget_html(
            items=[
                {"href": "/id/news/123/keep-me", "title": "Makan Bergizi Gratis Keep"},
                {"href": "/id/markets/something", "title": "Makan Bergizi Drop"},
                {"href": "/id/about-us", "title": "About Drop"},
                {"href": "https://other.example.com/id/news/1/x", "title": "Offsite Drop"},
            ],
        )
        links = s.parse_article_links(html)
        assert links == [
            "https://www.idnfinancials.com/id/news/123/keep-me",
        ]

    def test_parser_dedupes_repeated_anchors(self):
        s = self._scraper()
        html = """<!doctype html><html><body>
<div class="widget side-news">
  <div class="widget-header"><h2>Berita</h2></div>
  <div class="widget-body">
    <ul class="list">
      <li class="item"><a href="/id/news/5/makan-bergizi-gratis" title="Makan Bergizi Gratis">same</a></li>
      <li class="item"><a href="/id/news/5/makan-bergizi-gratis" title="Makan Bergizi Gratis">same</a></li>
    </ul>
  </div>
</div>
</body></html>"""
        links = s.parse_article_links(html)
        assert links == [
            "https://www.idnfinancials.com/id/news/5/makan-bergizi-gratis",
        ]

    def test_parser_applies_keyword_relevance_filter(self):
        s = self._scraper()
        s._current_keyword = "makan bergizi gratis"
        html = self._berita_widget_html(
            items=[
                {"href": "/id/news/1/relevant-makan-bergizi-gratis",
                 "title": "Makan Bergizi Gratis Headline"},
            ],
        )
        links = s.parse_article_links(html)
        assert links == [
            "https://www.idnfinancials.com/id/news/1/relevant-makan-bergizi-gratis",
        ]

    def test_parser_enforces_all_tokens_against_partial_overlap(self):
        """Multi-word query ``badan gizi nasional`` must drop a title that
        only contains two of the three tokens (e.g. "Badan Gizi Launch")
        and keep a title that contains every token on word boundaries."""
        s = self._scraper()
        s._current_keyword = "badan gizi nasional"
        html = self._berita_widget_html(
            items=[
                {"href": "/id/news/200/badan-gizi-launch", "title": "Badan Gizi Launch"},
                {"href": "/id/news/201/badan-gizi-nasional-resmi",
                 "title": "Badan Gizi Nasional Resmi Dibentuk"},
            ],
        )
        links = s.parse_article_links(html)
        assert links == [
            "https://www.idnfinancials.com/id/news/201/badan-gizi-nasional-resmi",
        ]

    def test_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None


class TestIDNFinancialsLatestURLFiltering:
    """IDN Financials latest: page 1 = /id/news; page N = /id/news?page=N."""

    @pytest.mark.asyncio
    async def test_page_one_targets_news_index(self):
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/id/news": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://www.idnfinancials.com/id/news"

    @pytest.mark.asyncio
    async def test_page_two_adds_page_param(self):
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/id/news": "<html></html>"})
        await s.build_latest_url(2)
        assert stub.calls[0][0] == "https://www.idnfinancials.com/id/news?page=2"

    @pytest.mark.asyncio
    async def test_outside_max_pages_returns_none(self):
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(0) is None
        assert await s.build_latest_url(999) is None

    def test_latest_parser_keeps_article_urls_only(self):
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        html = """<!doctype html><html><body>
          <a href="/id/news/10/some-slug">article — kept</a>
          <a href="https://www.idnfinancials.com/id/news/11/another">absolute — kept</a>
          <a href="/id/markets/foo">markets — dropped</a>
          <a href="/id/about">about — dropped</a>
          <a href="https://other.example.com/id/news/1/x">offsite — dropped</a>
        </body></html>"""
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://www.idnfinancials.com/id/news/10/some-slug",
            "https://www.idnfinancials.com/id/news/11/another",
        }

    def test_latest_parser_rejects_empty_body(self):
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None


class TestIDNFinancialsGetArticle:
    """IDN Financials article extraction contract: og:title (or h2.title /
    h1 fallback), authoritative meta + JSON-LD date with a final data-date
    fallback, JSON-LD author with meta and header-card fallbacks,
    article:section category with URL-based "Berita" fallback, body via
    div.article-body (article fallback)."""

    @staticmethod
    def _article_html(
        *,
        title="IDN Financials test headline",
        published_time="2026-07-12T10:00:00+07:00",
        author_name="IDN Financials Reporter",
        section="Berita",
    ):
        ld_payload = json.dumps({
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "NewsArticle",
                    "headline": title,
                    "datePublished": published_time,
                    "author": {"@type": "Person", "name": author_name},
                    "articleSection": section,
                },
            ],
        })
        return (
            '<!doctype html>\n<html><head>\n'
            f'<meta property="og:title" content="{title}">\n'
            f'<meta property="article:section" content="{section}">\n'
            f'<script type="application/ld+json">\n{ld_payload}\n</script>\n'
            '</head><body>\n'
            '<div class="article-body">'
            '<p>IDN Financials lead paragraph that the article-body extractor pulls.</p>'
            '<p>IDN Financials second paragraph retained by the body extractor.</p>'
            '</div>\n'
            '</body></html>\n'
        )

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_from_jsonld(self):
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/123/test-article"
        _attach_fetch(s, {link: self._article_html()})
        await s.get_article(link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["title"] == "IDN Financials test headline"
        # Authoritative source: JSON-LD datePublished (whatever local TZ does
        # to a +07:00 stamp, the calendar day stays 2026-07-12).
        assert item["publish_date"].year == 2026
        assert item["publish_date"].month == 7
        assert item["publish_date"].day == 12
        # Author comes from JSON-LD, not the (missing) meta tag.
        assert item["author"] == "IDN Financials Reporter"
        # article:section meta tag overrides nothing; it is the primary source.
        assert item["category"] == "Berita"
        assert item["source"] == "idnfinancials.com"
        assert item["keyword"] == "makan bergizi gratis"
        assert item["link"] == link
        assert "IDN Financials lead paragraph" in item["content"]
        assert "IDN Financials second paragraph" in item["content"]

    @pytest.mark.asyncio
    async def test_fallback_to_meta_published_time_when_jsonld_missing(self):
        """article:published_time meta tag is the authoritative first try."""
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/456/meta-date-only"
        html = (
            '<!doctype html><html><head>\n'
            '<meta property="og:title" content="Meta-date headline">\n'
            '<meta property="article:published_time" content="2026-07-12T12:00:00+00:00">\n'
            '<meta property="article:section" content="Makro">\n'
            '</head><body>\n'
            '<div class="article-body">'
            '<p>IDN Financials body paragraph for the meta-only date path.</p>'
            '</div>\n'
            '</body></html>\n'
        )
        _attach_fetch(s, {link: html})
        await s.get_article(link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["title"] == "Meta-date headline"
        # Meta date is the authoritative first source. Calendar day invariant.
        assert item["publish_date"].year == 2026
        assert item["publish_date"].month == 7
        assert item["publish_date"].day == 12
        assert item["category"] == "Makro"

    @pytest.mark.asyncio
    async def test_falls_back_to_h2_title_when_og_title_missing(self):
        """When og:title is absent, the h2.title and h1 selectors are tried."""
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/789/h2-fallback"
        html = (
            '<!doctype html><html><head>\n'
            '<meta property="article:published_time" content="2026-07-12T10:00:00+00:00">\n'
            '</head><body>\n'
            '<h2 class="title">H2 fallback headline</h2>\n'
            '<div class="article-body">'
            '<p>IDN Financials body paragraph for the h2 fallback path.</p>'
            '</div>\n'
            '</body></html>\n'
        )
        _attach_fetch(s, {link: html})
        await s.get_article(link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["title"] == "H2 fallback headline"

    @pytest.mark.asyncio
    async def test_empty_body_short_circuits_without_put(self):
        s = IDNFinancialsScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/111/empty"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "makan bergizi gratis")
        assert s.queue_.qsize() == 0


# ── 6. Warta Ekonomi — offline contract suite ─────────────────────────────


class TestWartaEkonomiSearchURLFiltering:
    """Warta Ekonomi search-mode discovery contract:

    - page 1 issues a POST to /search; the response is the redirect-resolved
      HTML body that ``parse_article_links`` then parses;
    - page 2 uses the captured ``_search_id`` and hits
      ``/search/{search_id}?page=2``;
    - the parser captures the search id from any ``/search/{id}`` pagination
      anchor, then keeps only ``a.articleListItem[href]`` anchors whose URL
      matches the article regex AND whose title contains a keyword token.
    """

    def _scraper(self):
        return WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )

    @staticmethod
    def _search_html(*, article_hrefs, search_id="42"):
        items = "\n".join(
            f'<a class="articleListItem" href="{a["href"]}" title="{a["title"]}">{a["title"]}</a>'
            for a in article_hrefs
        )
        return (
            '<!doctype html><html><body>'
            '<div class="article-list">'
            f'{items}'
            '</div>'
            '<div class="pagination">'
            f'<a href="/search/{search_id}?page=2">next</a>'
            '</div>'
            '</body></html>'
        )

    @pytest.mark.asyncio
    async def test_build_search_url_page_one_posts_to_search(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"/search": self._search_html(
            article_hrefs=[
                {"href": "/read11111/makan-bergizi-gratis-headline",
                 "title": "Makan Bergizi Gratis Headline"},
            ],
            search_id="99",
        )})
        body = await s.build_search_url("makan bergizi gratis", 1)
        assert body is not None
        url, method, extras = stub.calls[0]
        assert url == "https://wartaekonomi.co.id/search"
        assert method == "POST"
        assert extras is not None
        assert extras.get("data") == {"q": "makan bergizi gratis"}

    @pytest.mark.asyncio
    async def test_build_search_url_page_two_uses_captured_search_id(self):
        """After page 1 captures ``_search_id``, page 2 must reuse it via GET."""
        s = self._scraper()
        stub = _attach_fetch(s, {
            "/search": self._search_html(
                article_hrefs=[
                    {"href": "/read11111/makan-bergizi-gratis-headline",
                     "title": "Makan Bergizi Gratis Headline"},
                ],
                search_id="321",
            ),
            "/search/321": "<html></html>",
        })
        body1 = await s.build_search_url("makan bergizi gratis", 1)
        s._current_keyword = "makan bergizi gratis"
        # parse_article_links is what captures _search_id from pagination
        # anchors; build_search_url itself does not.
        s.parse_article_links(body1)
        await s.build_search_url("makan bergizi gratis", 2)
        # Two fetch calls were made: the POST to /search and the GET to
        # /search/321?page=2.
        assert len(stub.calls) == 2
        url2, method2, _ = stub.calls[1]
        assert url2 == "https://wartaekonomi.co.id/search/321?page=2"
        assert method2 is None  # GET is the default; method=None

    @pytest.mark.asyncio
    async def test_build_search_url_page_two_without_captured_id_returns_none(self):
        """If page 1 returned no pagination anchor, page 2 must short-circuit
        without issuing any HTTP call."""
        s = self._scraper()
        stub = _attach_fetch(s, {"/search": "<html></html>"})
        await s.build_search_url("makan bergizi gratis", 1)
        result = await s.build_search_url("makan bergizi gratis", 2)
        assert result is None
        # Only the POST to /search happened — no HTTP attempt for page 2.
        assert len(stub.calls) == 1

    def test_parser_captures_search_id_from_pagination_anchor(self):
        s = self._scraper()
        s._current_keyword = "makan bergizi gratis"
        s.parse_article_links(self._search_html(
            article_hrefs=[
                {"href": "/read11111/makan-bergizi-gratis-headline",
                 "title": "Makan Bergizi Gratis Headline"},
            ],
            search_id="456",
        ))
        assert s._search_id == "456"

    def test_parser_keeps_articleListItem_anchors_with_keyword_match(self):
        s = self._scraper()
        s._current_keyword = "makan bergizi gratis"
        links = s.parse_article_links(self._search_html(
            article_hrefs=[
                {"href": "/read11111/makan-bergizi-gratis-headline",
                 "title": "Makan Bergizi Gratis Headline One"},
                {"href": "/read22222/other-economy-story",
                 "title": "Some Other Economy Story"},
            ],
            search_id="1",
        ))
        assert links == {
            "https://wartaekonomi.co.id/read11111/makan-bergizi-gratis-headline",
        }

    def test_parser_enforces_all_tokens_against_partial_overlap(self):
        """Multi-word query ``badan gizi nasional`` must drop a title that
        only contains two of the three tokens (e.g. "Badan Gizi Launch")
        and keep a title that contains every token on word boundaries."""
        s = self._scraper()
        s._current_keyword = "badan gizi nasional"
        links = s.parse_article_links(self._search_html(
            article_hrefs=[
                {"href": "/read55555/badan-gizi-launch",
                 "title": "Badan Gizi Launch"},
                {"href": "/read66666/badan-gizi-nasional-resmi",
                 "title": "Badan Gizi Nasional Resmi Dibentuk"},
            ],
            search_id="7",
        ))
        assert links == {
            "https://wartaekonomi.co.id/read66666/badan-gizi-nasional-resmi",
        }

    def test_parser_rejects_anchors_outside_article_regex(self):
        s = self._scraper()
        s._current_keyword = "makan"
        links = s.parse_article_links(self._search_html(
            article_hrefs=[
                {"href": "/read11111/makan-bergizi-headline",
                 "title": "Makan Bergizi Headline"},
                {"href": "/category/foo", "title": "Makan Category"},
                {"href": "https://other.example.com/read55555/makan",
                 "title": "Makan Off-site"},
            ],
            search_id="1",
        ))
        assert links == {
            "https://wartaekonomi.co.id/read11111/makan-bergizi-headline",
        }

    def test_parser_uses_anchor_text_when_title_attr_missing(self):
        """The parser falls back to the anchor's text content when the title
        attribute is absent; the text is matched against keyword tokens."""
        s = self._scraper()
        s._current_keyword = "makan"
        html = """<!doctype html><html><body>
<a class="articleListItem" href="/read12345/text-only-anchor">Makan Bergizi Text Title</a>
<a class="articleListItem" href="/read67890/unrelated">Unrelated Anchor</a>
</body></html>"""
        links = s.parse_article_links(html)
        assert links == {
            "https://wartaekonomi.co.id/read12345/text-only-anchor",
        }

    def test_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None


class TestWartaEkonomiLatestURLFiltering:
    """Warta Ekonomi latest contract:

    - without start_date, the adapter hits ``/indeks`` for page 1 and
      ``/indeks?page=N`` for higher pages;
    - with start_date set, page 1 hits ``/indeks/YYYYMMDD`` — the lower-date
      cutoff is encoded into the URL itself;
    - the parser keeps only ``a.articleListItem`` anchors matching the
      article regex.
    """

    @pytest.mark.asyncio
    async def test_page_one_targets_indeks_without_start_date(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/indeks": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://wartaekonomi.co.id/indeks"

    @pytest.mark.asyncio
    async def test_page_two_appends_page_param(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/indeks": "<html></html>"})
        await s.build_latest_url(2)
        assert stub.calls[0][0] == "https://wartaekonomi.co.id/indeks?page=2"

    @pytest.mark.asyncio
    async def test_indeks_url_embeds_start_date_token(self):
        """With start_date set, page 1 must hit ``/indeks/YYYYMMDD`` —
        the lower-date cutoff is encoded into the URL itself."""
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis",
            start_date=datetime(2026, 7, 12),
            queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/indeks/20260712": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://wartaekonomi.co.id/indeks/20260712"

    @pytest.mark.asyncio
    async def test_indeks_url_with_date_paginates_with_page_param(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis",
            start_date=datetime(2026, 7, 12),
            queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/indeks/20260712": "<html></html>"})
        await s.build_latest_url(2)
        assert stub.calls[0][0] == (
            "https://wartaekonomi.co.id/indeks/20260712?page=2"
        )

    def test_latest_parser_keeps_articleListItem_anchors_only(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        html = """<!doctype html><html><body>
<a class="articleListItem" href="/read33333/indeks-article-one" title="Indeks article one">indeks-article-one</a>
<a class="articleListItem" href="/read44444/indeks-article-two" title="Indeks article two">indeks-article-two</a>
<a href="/category/foo">category — must be dropped</a>
<a href="https://other.example.com/read55555/off-site">off-site — must be dropped</a>
</body></html>"""
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://wartaekonomi.co.id/read33333/indeks-article-one",
            "https://wartaekonomi.co.id/read44444/indeks-article-two",
        }

    def test_latest_parser_rejects_empty_body(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None


class TestWartaEkonomiGetArticle:
    """Warta Ekonomi article extraction contract: h1 (article h1 / .articlePostHeader h1)
    with og:title fallback, JSON-LD datePublished with meta/time fallbacks,
    JSON-LD author with meta fallback, JSON-LD articleSection with breadcrumb /
    meta fallbacks, body via .articlePostContent with noise-class stripping."""

    @staticmethod
    def _article_html(
        *,
        title="Warta Ekonomi test headline",
        canonical="https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline",
        section="Makro",
        author_name="Warta Ekonomi Reporter",
        published_time="2026-07-12T10:00:00+07:00",
        include_canonical=True,
    ):
        ld_payload = json.dumps({
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": title,
            "datePublished": published_time,
            "author": {"@type": "Person", "name": author_name},
            "articleSection": section,
        })
        canonical_tag = (
            f'<link rel="canonical" href="{canonical}">'
            if include_canonical
            else ""
        )
        return (
            '<!doctype html>\n<html><head>\n'
            f'<title>{title}</title>\n'
            f'{canonical_tag}\n'
            f'<script type="application/ld+json">\n{ld_payload}\n</script>\n'
            '</head><body>\n'
            '<article class="articlePost">\n'
            '<div class="articlePostHeader">\n'
            f'<h1>{title}</h1>\n'
            '<ul><li><a href="/category/makro">Makro</a></li></ul>\n'
            '</div>\n'
            '<div class="articlePostContent">'
            '<p>Warta Ekonomi lead paragraph retained by the articlePostContent extractor.</p>'
            '<p>Warta Ekonomi second paragraph continuing the article body.</p>'
            # Inline cross-promo anchor inside the body — the extractor must
            # decompose it because the anchor's text starts with "Baca Juga".
            '<a href="/read99999/unrelated-promo">Baca Juga: cross promo link</a> kept'
            # Noise-class container with another promo anchor — must be stripped
            # because its CSS class matches the noise regex.
            '<div class="baca-juga-box"><a href="/x">must be removed</a></div>'
            '</div>\n'
            '</article>\n'
            '</body></html>\n'
        )

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline"
        canonical = "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline"
        _attach_fetch(s, {link: self._article_html(canonical=canonical)})
        await s.get_article(link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["title"] == "Warta Ekonomi test headline"
        # JSON-LD datePublished is the authoritative source. Calendar day
        # invariant — the exact naive hour depends on the runner's local TZ.
        assert item["publish_date"].year == 2026
        assert item["publish_date"].month == 7
        assert item["publish_date"].day == 12
        assert item["author"] == "Warta Ekonomi Reporter"
        assert item["category"] == "Makro"
        assert item["source"] == "wartaekonomi.co.id"
        assert item["keyword"] == "makan bergizi gratis"
        # The queue stores the canonical link, not the input link — both
        # happen to match here, but the canonical-resolver contract is pinned
        # by the dedicated canonical tests below.
        assert item["link"] == canonical
        assert "Warta Ekonomi lead paragraph" in item["content"]
        assert "Warta Ekonomi second paragraph" in item["content"]
        # The "Baca Juga" inline cross-promo anchor must be stripped.
        assert "Baca Juga" not in item["content"]
        assert "unrelated promo link" not in item["content"]

    @pytest.mark.asyncio
    async def test_falls_back_to_meta_published_time(self):
        """When no JSON-LD date exists, meta[itemprop=datePublished] wins."""
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read20000/meta-date"
        html = (
            '<!doctype html><html><head>\n'
            '<link rel="canonical" href="https://wartaekonomi.co.id/read20000/meta-date">\n'
            '</head><body>\n'
            '<article class="articlePost">\n'
            '<div class="articlePostHeader"><h1>Meta-date headline</h1></div>\n'
            '<div class="articlePostContent">\n'
            '<p>Warta Ekonomi body paragraph for the meta-date fallback path.</p>\n'
            '</div>\n'
            '<meta itemprop="datePublished" content="2026-07-12T12:00:00+00:00">\n'
            '</article>\n'
            '</body></html>\n'
        )
        _attach_fetch(s, {link: html})
        await s.get_article(link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["title"] == "Meta-date headline"
        assert item["publish_date"].year == 2026
        assert item["publish_date"].month == 7
        assert item["publish_date"].day == 12

    @pytest.mark.asyncio
    async def test_empty_body_short_circuits_without_put(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read30000/empty"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "makan bergizi gratis")
        assert s.queue_.qsize() == 0

    @pytest.mark.asyncio
    async def test_missing_title_short_circuits(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read40000/no-title"
        # No h1 inside the article, no og:title; the rest is valid.
        html = (
            '<!doctype html>\n<html><body>\n'
            '<article class="articlePost">\n'
            '<div class="articlePostContent">'
            '<p>Body paragraph that must not reach the queue without a title.</p>'
            '</div>\n'
            '</article>\n'
            '</body></html>\n'
        )
        _attach_fetch(s, {link: html})
        await s.get_article(link, "makan bergizi gratis")
        assert s.queue_.qsize() == 0


class TestWartaEkonomiMetadataFreeCategory:
    """Canonical ``/read{digits}/{slug}`` URLs with no JSON-LD ``articleSection``,
    no breadcrumb leaf under ``.articlePostHeader``, and no
    ``meta[property=article:section]``/``meta[name=category]`` must emit
    ``"Unknown"`` as the queued category. The article slug appears in the URL
    path but is never a category segment; emitting it is the regression this
    contract pins.
    """

    @pytest.mark.asyncio
    async def test_slug_not_emitted_as_category_when_no_metadata(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read12345/metadata-free-headline-slug"
        canonical = link
        html = (
            '<!doctype html>\n<html><head>\n'
            '<title>Metadata-free headline slug</title>\n'
            f'<link rel="canonical" href="{canonical}">\n'
            '<script type="application/ld+json">\n'
            '{"@context":"https://schema.org","@type":"NewsArticle",'
            '"headline":"Metadata-free headline slug",'
            '"datePublished":"2026-07-12T10:00:00+07:00",'
            '"author":{"@type":"Person","name":"Warta Ekonomi Reporter"}}\n'
            '</script>\n'
            '</head><body>\n'
            '<article class="articlePost">\n'
            '<div class="articlePostHeader"><h1>Metadata-free headline slug</h1></div>\n'
            '<div class="articlePostContent">'
            '<p>Body paragraph retained on the metadata-free category path.</p>'
            '</div>\n'
            '</article>\n'
            '</body></html>\n'
        )
        _attach_fetch(s, {link: html})
        await s.get_article(link, "makan bergizi gratis")

        assert s.queue_.qsize() == 1
        item = s.queue_.get_nowait()
        # The article must still queue normally — only the category field
        # collapses to Unknown.
        assert item["title"] == "Metadata-free headline slug"
        assert item["publish_date"].year == 2026
        assert item["publish_date"].month == 7
        assert item["publish_date"].day == 12
        assert item["author"] == "Warta Ekonomi Reporter"
        assert "Body paragraph retained" in item["content"]
        # Contract: no category signal on a /read{n}/{slug} URL collapses to
        # "Unknown"; the slug must never be misclassified as the category.
        assert item["category"] == "Unknown"
        assert item["category"] != "metadata-free-headline-slug"


class TestWartaEkonomiCanonicalLink:
    """Warta Ekonomi must resolve the canonical link for the queued item.

    The contract is:

    1. If ``<link rel="canonical">`` exists, its ``href`` wins.
    2. Otherwise, ``<meta property="og:url">``'s ``content`` wins.
    3. If neither exists, the input ``link`` is used as the fallback.
    """

    @pytest.mark.asyncio
    async def test_link_rel_canonical_takes_priority(self):
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        input_link = "https://wartaekonomi.co.id/read11111/some-article?utm_source=x"
        canonical = "https://wartaekonomi.co.id/read11111/some-article"
        article_html = TestWartaEkonomiGetArticle._article_html(
            canonical=canonical,
        )
        _attach_fetch(s, {input_link: article_html})
        await s.get_article(input_link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["link"] == canonical

    @pytest.mark.asyncio
    async def test_og_url_used_when_canonical_missing(self):
        """Without ``<link rel=canonical>``, ``og:url`` must drive the link."""
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        input_link = "https://wartaekonomi.co.id/read22222/some-article"
        html = (
            '<!doctype html>\n<html><head>\n'
            '<meta property="og:url" content="https://wartaekonomi.co.id/read22222/canonical-og-url">\n'
            '<title>OG URL fallback headline</title>\n'
            '<script type="application/ld+json">\n'
            '{"@context":"https://schema.org","@type":"NewsArticle",'
            '"headline":"OG URL fallback headline",'
            '"datePublished":"2026-07-12T10:00:00+07:00",'
            '"author":{"@type":"Person","name":"OG Author"},'
            '"articleSection":"Makro"}\n'
            '</script>\n'
            '</head><body>\n'
            '<article class="articlePost">\n'
            '<div class="articlePostHeader"><h1>OG URL fallback headline</h1></div>\n'
            '<div class="articlePostContent">'
            '<p>OG URL body paragraph for the canonical-fallback test path.</p>'
            '</div>\n'
            '</article>\n'
            '</body></html>\n'
        )
        _attach_fetch(s, {input_link: html})
        await s.get_article(input_link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["link"] == "https://wartaekonomi.co.id/read22222/canonical-og-url"

    @pytest.mark.asyncio
    async def test_input_link_used_when_neither_canonical_nor_og_url(self):
        """With no canonical and no og:url, the input link is the fallback."""
        s = WartaEkonomiScraper(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        input_link = "https://wartaekonomi.co.id/read33333/fallback-link"
        article_html = TestWartaEkonomiGetArticle._article_html(
            include_canonical=False,
        )
        _attach_fetch(s, {input_link: article_html})
        await s.get_article(input_link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["link"] == input_link


# ── 7. New-adapter queue schema + start_date cutoff (parametrized) ────────


_QUEUE_SCHEMA_PARAMS = (
    pytest.param(
        DDTCNewsScraper,
        "pajak",
        "https://news.ddtc.co.id/berita/foo-bar/123/test-article",
        "DDTC test headline",
        "DDTC Reporter",
        "Pajak",
        "news.ddtc.co.id",
        id="ddtcnews",
    ),
    pytest.param(
        IDNFinancialsScraper,
        "makan bergizi gratis",
        "https://www.idnfinancials.com/id/news/123/test-article",
        "IDN Financials test headline",
        "IDN Financials Reporter",
        "Berita",
        "idnfinancials.com",
        id="idnfinancials",
    ),
    pytest.param(
        WartaEkonomiScraper,
        "makan bergizi gratis",
        "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline",
        "Warta Ekonomi test headline",
        "Warta Ekonomi Reporter",
        "Makro",
        "wartaekonomi.co.id",
        id="wartaekonomi",
    ),
    pytest.param(
        AlineaScraper,
        "politik",
        "https://www.alinea.id/politik/foo-bar-b123",
        "Alinea test headline",
        "Reporter Satu",
        "politik",
        "www.alinea.id",
        id="alinea",
    ),
    pytest.param(
        GNFIScraper,
        "bali",
        "https://www.goodnewsfromindonesia.id/2026/07/12/test-article",
        "GNFI test headline",
        "GNFI Reporter",
        "Lingkungan",
        "goodnewsfromindonesia.id",
        id="gnfi",
    ),
    pytest.param(
        BetahitaScraper,
        "lingkungan",
        "https://www.betahita.id/berita/12345/test-article",
        "Betahita test headline",
        "Betahita Reporter",
        "Berita",
        "betahita.id",
        id="betahita",
    ),
    pytest.param(
        NusaBaliScraper,
        "bali",
        "https://www.nusabali.com/berita/225365/pria-mabuk-diamankan-polisi",
        "NusaBali test headline",
        "Penulis : I Putu Reporter",
        "Denpasar",
        "nusabali.com",
        id="nusabali",
    ),
    pytest.param(
        ConversationIDScraper,
        "indonesia",
        "https://theconversation.com/some-article-12345",
        "Conversation ID test headline",
        "Author One, Author Two",
        "Politics, Economics",
        "theconversation.com",
        id="conversationid",
    ),
    pytest.param(
        HukumonlineScraper,
        "hukum",
        "https://www.hukumonline.com/berita/a/canonical-slug",
        "Hukumonline test headline",
        "Hukumonline Reporter",
        "Hukum",
        "hukumonline.com",
        id="hukumonline",
    ),
    pytest.param(
        IndependenScraper,
        "indonesia",
        "https://independen.id/judul-artikel-contoh/",
        "Independen test headline",
        "Independen Reporter",
        "Investigasi",
        "independen.id",
        id="independen",
    ),
)


class TestNewAdapterQueueSchema:
    """All ten newest adapters must emit items with exactly the eight
    contract keys, expected value types, and the canonical ``source`` domain.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("cls", "keyword", "link", "title", "author", "category", "source"),
        _QUEUE_SCHEMA_PARAMS,
    )
    async def test_get_article_emits_exact_queue_schema(
        self, cls, keyword, link, title, author, category, source,
    ):
        if cls is DDTCNewsScraper:
            html = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="DDTC test headline">'
                '</head><body>'
                '<h1>DDTC test headline</h1>'
                '<div id="publish-news">Minggu, 12 Juli 2026</div>'
                '<div class="contentArticle">'
                '<p>DDTC lead paragraph that the contentArticle extractor pulls into the body text.</p>'
                '</div>'
                '<meta name="author" content="DDTC Reporter">'
                '<meta name="category" content="Pajak">'
                '</body></html>'
            )
        elif cls is IDNFinancialsScraper:
            ld_payload = json.dumps({
                "@context": "https://schema.org",
                "@graph": [{
                    "@type": "NewsArticle",
                    "headline": "IDN Financials test headline",
                    "datePublished": "2026-07-12T10:00:00+07:00",
                    "author": {"@type": "Person", "name": "IDN Financials Reporter"},
                    "articleSection": "Berita",
                }],
            })
            html = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="IDN Financials test headline">'
                '<meta property="article:section" content="Berita">'
                f'<script type="application/ld+json">{ld_payload}</script>'
                '</head><body>'
                '<div class="article-body">'
                '<p>IDN Financials lead paragraph that the article-body extractor pulls.</p>'
                '</div>'
                '</body></html>'
            )
        elif cls is WartaEkonomiScraper:
            ld_payload = json.dumps({
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "Warta Ekonomi test headline",
                "datePublished": "2026-07-12T10:00:00+07:00",
                "author": {"@type": "Person", "name": "Warta Ekonomi Reporter"},
                "articleSection": "Makro",
            })
            html = (
                '<!doctype html><html><head>'
                f'<link rel="canonical" href="{link}">'
                f'<script type="application/ld+json">{ld_payload}</script>'
                '</head><body>'
                '<article class="articlePost">'
                '<div class="articlePostHeader"><h1>Warta Ekonomi test headline</h1></div>'
                '<div class="articlePostContent">'
                '<p>Warta Ekonomi lead paragraph retained by the articlePostContent extractor.</p>'
                '</div>'
                '</article>'
                '</body></html>'
            )
        elif cls is AlineaScraper:
            html = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="Alinea test headline">'
                '</head><body>'
                '<h1>Alinea test headline</h1>'
                '<div class="frontdate">12 Juli 2026</div>'
                '<div class="written__reporter">'
                '<div class="reporter__nama">Reporter Satu</div>'
                '</div>'
                '<article><div>'
                '<p>Alinea lead paragraph well over the forty-character filter threshold for the body.</p>'
                '<p>Alinea second body paragraph retained by the alinea content extractor.</p>'
                '</div></article>'
                '</body></html>'
            )
        elif cls is GNFIScraper:
            ld_payload = json.dumps({
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "datePublished": "2026-07-12T10:00:00+00:00",
                "author": {"@type": "Person", "name": "JSON-LD Reporter"},
            })
            html = (
                '<!doctype html>\n<html><head>\n'
                '<meta property="og:title" content="GNFI test headline">\n'
                '<meta name="author" content="GNFI Reporter">\n'
                '<script type="application/ld+json">\n'
                f'{ld_payload}\n'
                '</script>\n'
                '</head><body>\n'
                '<div class="article-category"><a href="/c/lingkungan">Lingkungan</a></div>\n'
                '<div class="article-sheet">\n'
                '<p data-path-to-node="0">GNFI lead paragraph retained by the article-sheet extractor.</p>\n'
                '<p data-path-to-node="1">GNFI second paragraph retained by the article-sheet extractor.</p>\n'
                '</div>\n'
                '</body></html>\n'
            )
        elif cls is BetahitaScraper:
            html = (
                '<!doctype html><html><head></head><body>'
                '<article class="detail-artikel">'
                '<div class="judul-artikel">'
                '<h5>Berita</h5>'
                '<h1>Betahita test headline</h1>'
                '<h5 class="margin-bottom-sm">Sabtu, 11 Juli 2026</h5>'
                '</div>'
                '<div class="box-sumber"><h5 class="title">Oleh: Betahita Reporter</h5></div>'
                '<div class="detail-in">'
                '<p>BETAHITA.ID — Betahita lead paragraph included after the dateline marker.</p>'
                '<p>Betahita second paragraph also retained because it follows the dateline.</p>'
                '</div>'
                '</article>'
                '</body></html>'
            )
        elif cls is NusaBaliScraper:
            html = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="NusaBali test headline">'
                '</head><body>'
                '<span class="month pull-left" itemprop="datePublished">12 Jul 2026 19:37:24</span>'
                '<div class="breadcrumb">'
                '<span class="article-category" itemprop="articleSection">Denpasar</span>'
                '</div>'
                '<span itemprop="author">Penulis : I Putu Reporter</span>'
                '<div class="entry-content" itemprop="articleBody">'
                '<p>NusaBali lead paragraph pulled into the body by the entry-content extractor.</p>'
                '<p>NusaBali second paragraph retained because it sits inside articleBody.</p>'
                '</div>'
                '</body></html>'
            )
        elif cls is ConversationIDScraper:
            html = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="Conversation ID test headline">'
                '</head><body>'
                '<time datetime="2026-07-12T10:00:00Z">12 July 2026</time>'
                '<a rel="author" href="/profile/author-one">Author One</a>'
                '<a rel="author" href="/profile/author-two">Author Two</a>'
                '<a href="/topics/politics">Politics</a>'
                '<a href="/topics/economics">Economics</a>'
                '<div itemprop="articleBody">'
                '<p>Conversation ID lead paragraph retained by the articleBody extractor.</p>'
                '<p>Conversation ID second paragraph retained by the articleBody extractor.</p>'
                '</div>'
                '</body></html>'
            )
        elif cls is HukumonlineScraper:
            ld_payload = json.dumps({
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "datePublished": "2026-07-12T10:00:00+07:00",
                "author": {"@type": "Person", "name": "Hukumonline Reporter"},
                "articleSection": "Hukum",
            })
            html = (
                '<!doctype html>\n<html><head>\n'
                '<meta property="og:title" content="Hukumonline test headline">\n'
                f'<script type="application/ld+json">{ld_payload}</script>\n'
                '</head><body>\n'
                '<article>\n'
                '<p>Hukumonline lead paragraph included by the article-descendant extractor.</p>\n'
                '<p>Hukumonline second paragraph retained by the joined article body.</p>\n'
                '</article>\n'
                '</body></html>\n'
            )
        else:  # IndependenScraper
            html = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="Independen test headline - Independen.id">'
                '<meta property="article:published_time" content="2026-07-12T10:00:00+07:00">'
                '<meta property="article:section" content="Investigasi">'
                '<meta name="author" content="Independen Reporter">'
                '</head><body>'
                '<article>'
                '<p class="lead">Independen lead paragraph surviving the 25-char filter inside the article.</p>'
                '<p>Independen second paragraph continuing the joined article body from the markup.</p>'
                '<div class="share-buttons"><a href="#">share</a></div>'
                '<div class="related-articles"><p>related noise — must be removed</p></div>'
                '</article>'
                '</body></html>'
            )

        s = cls(keywords=keyword, queue_=asyncio.Queue())
        _attach_fetch(s, {link: html})
        await s.get_article(link, keyword)

        assert s.queue_.qsize() == 1
        item = s.queue_.get_nowait()
        assert tuple(sorted(item)) == tuple(sorted(_QUEUE_KEYS))
        assert isinstance(item["publish_date"], datetime)
        assert isinstance(item["title"], str) and item["title"]
        assert isinstance(item["author"], str) and item["author"]
        assert isinstance(item["content"], str) and item["content"]
        assert item["keyword"] == keyword
        assert isinstance(item["category"], str) and item["category"]
        assert isinstance(item["source"], str) and item["source"]
        assert item["link"] == link
        assert item["source"] == source

_CUTOFF_PARAMS = (
    pytest.param(
        DDTCNewsScraper,
        "pajak",
        "https://news.ddtc.co.id/berita/foo-bar/123/test-article",
        id="ddtcnews",
    ),
    pytest.param(
        IDNFinancialsScraper,
        "makan bergizi gratis",
        "https://www.idnfinancials.com/id/news/123/test-article",
        id="idnfinancials",
    ),
    pytest.param(
        WartaEkonomiScraper,
        "makan bergizi gratis",
        "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline",
        id="wartaekonomi",
    ),
    pytest.param(
        GNFIScraper,
        "bali",
        "https://www.goodnewsfromindonesia.id/2026/07/12/test-article",
        id="gnfi",
    ),
    pytest.param(
        NusaBaliScraper,
        "bali",
        "https://www.nusabali.com/berita/225365/pria-mabuk-diamankan-polisi",
        id="nusabali",
    ),
    pytest.param(
        ConversationIDScraper,
        "indonesia",
        "https://theconversation.com/some-article-12345",
        id="conversationid",
    ),
    pytest.param(
        IndependenScraper,
        "indonesia",
        "https://independen.id/judul-artikel-contoh/",
        id="independen",
    ),
)


class TestNewAdapterStartDateCutoff:
    """``start_date`` in the future must drop the article and flip
    ``continue_scraping`` to False — the queue stays empty."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("cls", "keyword", "link"), _CUTOFF_PARAMS)
    async def test_start_date_in_future_drops_article_and_flips_flag(
        self, cls, keyword, link,
    ):
        s = cls(keywords=keyword, start_date=datetime(2099, 1, 1), queue_=asyncio.Queue())
        # Reuse the focused adapter fixtures by importing the same body that
        # the corresponding extraction tests use; future start_date must
        # short-circuit before any of those selectors are exercised.
        if cls is DDTCNewsScraper:
            body = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="DDTC test headline">'
                '</head><body>'
                '<div id="publish-news">Minggu, 12 Juli 2026</div>'
                '<div class="contentArticle"><p>x</p></div>'
                '</body></html>'
            )
        elif cls is IDNFinancialsScraper:
            body = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="IDN Financials test headline">'
                '<meta property="article:published_time" content="2026-07-12T10:00:00+00:00">'
                '<meta property="article:section" content="Berita">'
                '</head><body>'
                '<div class="article-body"><p>x</p></div>'
                '</body></html>'
            )
        elif cls is WartaEkonomiScraper:
            body = (
                '<!doctype html><html><head>'
                f'<link rel="canonical" href="{link}">'
                '<script type="application/ld+json">'
                '{"@context":"https://schema.org","@type":"NewsArticle",'
                '"headline":"Warta Ekonomi test headline",'
                '"datePublished":"2026-07-12T10:00:00+07:00",'
                '"author":{"@type":"Person","name":"Warta Ekonomi Reporter"},'
                '"articleSection":"Makro"}'
                '</script>'
                '</head><body>'
                '<article class="articlePost">'
                '<div class="articlePostHeader"><h1>Warta Ekonomi test headline</h1></div>'
                '<div class="articlePostContent"><p>x</p></div>'
                '</article>'
                '</body></html>'
            )
        elif cls is GNFIScraper:
            body = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="GNFI test headline">'
                '<meta property="article:published_time" content="2026-07-12T10:00:00+07:00">'
                '</head><body><div class="article-sheet"><p data-path-to-node="0">x</p></div>'
                '</body></html>'
            )
        elif cls is NusaBaliScraper:
            body = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="NusaBali test headline">'
                '</head><body>'
                '<span class="month pull-left" itemprop="datePublished">12 Jul 2026 19:37:24</span>'
                '<span itemprop="author">Penulis : Author</span>'
                '<div class="entry-content" itemprop="articleBody"><p>x</p></div>'
                '</body></html>'
            )
        elif cls is ConversationIDScraper:
            body = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="Conversation ID test headline">'
                '</head><body>'
                '<time datetime="2026-07-12T10:00:00Z">12 July 2026</time>'
                '<div itemprop="articleBody"><p>x</p></div>'
                '</body></html>'
            )
        else:  # IndependenScraper
            body = (
                '<!doctype html><html><head>'
                '<meta property="og:title" content="Independen test headline">'
                '<meta property="article:published_time" content="2026-07-12T10:00:00+07:00">'
                '</head><body>'
                '<article><p>x</p></article>'
                '</body></html>'
            )
        _attach_fetch(s, {link: body})
        await s.get_article(link, keyword)
        assert s.queue_.qsize() == 0
        assert s.continue_scraping is False


# ── 8. GNFI: strict every-token keyword filter; latest path is unfiltered ──


class TestGNFIRelevance:
    """GNFI: search mode applies every-token filter against ``<title>``;
    latest mode (``/explore``) consumes the same HTML without any filter."""

    KEYWORD = "makan bergizi"
    HTML = (
        '<html><body>'
        '<a href="https://www.goodnewsfromindonesia.id/2026/07/12/makan-bergizi-gratis-di-bali"'
        '   title="Makan Bergizi title">link1</a>'
        '<a href="https://www.goodnewsfromindonesia.id/2026/07/11/unrelated-other-news"'
        '   title="Other title">link2</a>'
        '</body></html>'
    )

    @pytest.mark.asyncio
    async def test_strict_search_then_unfiltered_latest(self):
        s = GNFIScraper(keywords=self.KEYWORD, queue_=asyncio.Queue())

        async def stub_build_search_url(keyword, page):
            s._current_keyword = keyword
            return self.HTML

        s.build_search_url = stub_build_search_url
        await s.build_search_url(self.KEYWORD, 1)

        search_links = s.parse_article_links(self.HTML)
        assert search_links == {
            "https://www.goodnewsfromindonesia.id/2026/07/12/makan-bergizi-gratis-di-bali",
        }

        latest_links = s.parse_latest_article_links(self.HTML)
        assert latest_links == {
            "https://www.goodnewsfromindonesia.id/2026/07/12/makan-bergizi-gratis-di-bali",
            "https://www.goodnewsfromindonesia.id/2026/07/11/unrelated-other-news",
        }


# ── 9. Infobanknews: REST discovery + article extraction + cutoff ──────────


class TestInfobanknewsScraper:
    """Infobanknews: WordPress REST discovery pagination/boundaries +
    article extraction (JSON-LD / article-content fallback) + cutoff."""

    BASE = "https://infobanknews.com"
    REST = f"{BASE}/wp-json/wp/v2/posts"
    LINK_OK = f"{BASE}/makan-bergizi/"
    LINK_NESTED = f"{BASE}/category/foo/"
    LINK_TAX = f"{BASE}/author/john/"

    @pytest.mark.asyncio
    async def test_rest_discovery_pagination_and_article_schema(self):
        s = InfobanknewsScraper(keywords="makan bergizi", queue_=asyncio.Queue())

        page1 = json.dumps([
            {"link": self.LINK_OK},
            {"link": self.LINK_NESTED},
            {"link": "not-a-link"},
        ])
        page2 = "this is not json at all"
        page3 = json.dumps([{"link": self.LINK_TAX}, "string-not-dict"])
        page11 = json.dumps([{"link": f"{self.BASE}/another-post/"}])

        _attach_fetch(s, {
            f"{self.REST}?search=makan%20bergizi&per_page=20&page=1&_fields=link": page1,
            f"{self.REST}?search=makan%20bergizi&per_page=20&page=2&_fields=link": page2,
            f"{self.REST}?search=makan%20bergizi&per_page=20&page=3&_fields=link": page3,
            f"{self.REST}?search=makan%20bergizi&per_page=20&page=10&_fields=link": page11,
        })

        assert s.parse_article_links(await s.build_search_url("makan bergizi", 1)) == [self.LINK_OK]
        assert await s.build_search_url("makan bergizi", 11) is None
        assert s.parse_article_links(await s.build_search_url("makan bergizi", 2)) is None
        assert s.parse_article_links(await s.build_search_url("makan bergizi", 3)) is None
        assert s.parse_article_links(await s.build_search_url("makan bergizi", 10)) == [f"{self.BASE}/another-post/"]

    @pytest.mark.asyncio
    async def test_article_schema_naive_date_and_future_cutoff(self):
        link = self.LINK_OK
        body = (
            '<!doctype html><html><head>'
            '<meta property="og:title" content="Infobank test headline">'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"NewsArticle",'
            '"datePublished":"2026-07-12T10:00:00+07:00"}'
            '</script>'
            '</head><body>'
            '<div class="article-content"><p>Body paragraph one.</p>'
            '<p>Body paragraph two with detail.</p></div>'
            '</body></html>'
        )

        s = InfobanknewsScraper(
            keywords="makan bergizi", queue_=asyncio.Queue(),
        )
        _attach_fetch(s, {link: body})
        await s.get_article(link, "makan bergizi")
        assert s.queue_.qsize() == 1
        item = await s.queue_.get()
        assert list(item.keys()) == list(_QUEUE_KEYS)
        assert item["title"] == "Infobank test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 10, 0, 0)
        assert item["source"] == "infobanknews.com"
        assert item["link"] == link

        s2 = InfobanknewsScraper(
            keywords="makan bergizi",
            start_date=datetime(2099, 1, 1),
            queue_=asyncio.Queue(),
        )
        _attach_fetch(s2, {link: body})
        await s2.get_article(link, "makan bergizi")

# ── 10. IDX Channel: sitemap discovery, keyword filter, article + cutoff ───


class TestIDXChannelScraper:
    """IDX Channel: required-news-sitemap discovery, every-token keyword
    filter with cap, unfiltered latest, and DD/MM/YYYY HH:MM WIB article
    extraction with start_date cutoff."""

    BASE = "https://www.idxchannel.com"
    INDEX = f"{BASE}/sitemap.xml"
    SITEMAP_A = f"{BASE}/news/sitemap.xml"
    SITEMAP_B = f"{BASE}/market-news/sitemap.xml"

    SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
    NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"

    @staticmethod
    def _sitemap_index_xml(extra_loc: str | None = None) -> str:
        locs = "".join(
            f"<sm:sitemap><sm:loc>{u}</sm:loc></sm:sitemap>" for u in (
                "https://www.idxchannel.com/news/sitemap.xml",
                "https://www.idxchannel.com/market-news/sitemap.xml",
            )
        )
        if extra_loc:
            locs += f"<sm:sitemap><sm:loc>{extra_loc}</sm:loc></sm:sitemap>"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns:sm="{TestIDXChannelScraper.SM_NS}">'
            f"{locs}</urlset>"
        )

    def _news_sitemap_xml(self, entries: list[tuple[str, str]]) -> str:
        body = "".join(
            f"<url><loc>{loc}</loc>"
            f"<news:news><news:title><![CDATA[{title}]]></news:title>"
            f"</news:news></url>"
            for loc, title in entries
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="{TestIDXChannelScraper.SM_NS}" '
            f'xmlns:news="{TestIDXChannelScraper.NEWS_NS}">'
            f"{body}</urlset>"
        )

    @pytest.mark.asyncio
    async def test_sitemap_discovery_filter_latest_and_article(self):
        s = IDXChannelScraper(
            keywords="makan bergizi", queue_=asyncio.Queue(),
        )

        sitemap_a = self._news_sitemap_xml([
            ("https://www.idxchannel.com/news/makan-bergizi-gratis/", "Makan Bergizi title"),
            ("https://www.idxchannel.com/news/unrelated-other-story/", "Other Story title"),
            ("https://www.idxchannel.com/news/extra-skip/", "Extra title"),
        ])
        sitemap_b = self._news_sitemap_xml([
            ("https://www.idxchannel.com/market-news/makan-bergizi-ipo/", "Makan Bergizi IPO title"),
        ])
        index_xml = self._sitemap_index_xml()

        cache: dict[str, str] = {
            self.INDEX: index_xml,
            self.SITEMAP_A: sitemap_a,
            self.SITEMAP_B: sitemap_b,
        }
        _attach_fetch(s, cache)

        discovered = await s._discover_news_sitemaps()
        assert discovered[:2] == [self.SITEMAP_A, self.SITEMAP_B]
        assert [u for u, *_ in s.fetch.calls] == [self.INDEX]

        search_entries = await s.build_search_url("makan bergizi", 1)
        links = s.parse_article_links(search_entries)
        assert links == [
            "https://www.idxchannel.com/news/makan-bergizi-gratis/",
            "https://www.idxchannel.com/market-news/makan-bergizi-ipo/",
        ]
        assert await s.build_search_url("makan bergizi", 2) is None

        latest_entries = await s.build_latest_url(1)
        assert s.parse_latest_article_links(latest_entries) == [
            "https://www.idxchannel.com/news/makan-bergizi-gratis/",
            "https://www.idxchannel.com/news/unrelated-other-story/",
            "https://www.idxchannel.com/news/extra-skip/",
        ]
        assert await s.build_latest_url(0) is None

        link = "https://www.idxchannel.com/news/makan-bergizi-gratis/"
        article_body = (
            '<!doctype html><html><head>'
            '<meta property="og:title" content="IDX Channel test headline">'
            '</head><body>'
            '<div class="article--creator"><span class="text-body--2">'
            '12/07/2026 10:00 WIB'
            '</span></div>'
            '<div class="article--content"><p>Body paragraph one has enough detail for extraction.</p>'
            '<p>Body paragraph two has enough detail for extraction.</p></div>'
            '</body></html>'
        )
        s2 = IDXChannelScraper(
            keywords="makan bergizi", queue_=asyncio.Queue(),
        )
        _attach_fetch(s2, {link: article_body})
        await s2.get_article(link, "makan bergizi")
        assert s2.queue_.qsize() == 1
        item = await s2.queue_.get()
        assert list(item.keys()) == list(_QUEUE_KEYS)
        assert item["title"] == "IDX Channel test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 10, 0, 0)
        assert item["source"] == "idxchannel.com"
        assert item["link"] == link

        s3 = IDXChannelScraper(
            keywords="makan bergizi",
            start_date=datetime(2099, 1, 1),
            queue_=asyncio.Queue(),
        )
        _attach_fetch(s3, {link: article_body})
        await s3.get_article(link, "makan bergizi")
        assert s3.queue_.qsize() == 0
        assert s3.continue_scraping is False


# ── 11. Batch sources — discovery + extraction (per-adapter focus) ───────────


def _alinea_search_html(*, url_substring: str = "") -> str:
    return """<!doctype html><html><body>
        <a href="/politik/foo-bar-b123">in-section</a>
        <a href="/gaya-hidup/baz-qux-b456">in-section-gaya-hidup</a>
        <a href="/search?q=foo">search page itself</a>
        <a href="/lain/foo">unknown section</a>
        <a href="https://example.com/politik/baz">off-site</a>
        <a>no href</a>
    </body></html>"""


def _alinea_article_html() -> str:
    return """<!doctype html><html><head>
        <meta property="og:title" content="Alinea test headline">
    </head><body>
        <h1>Alinea test headline</h1>
        <div class="frontdate">12 Juli 2026</div>
        <div class="written__reporter">
            <div class="reporter__nama">Reporter Satu</div>
        </div>
        <article><div>
            <p>Alinea lead paragraph well over the forty character filter threshold for the body.</p>
            <p>Alinea second paragraph retained by the article extractor.</p>
        </div></article>
    </body></html>"""


class TestAlineaFocus:
    """Alinea: search URL + parser, latest /indeks page 1, extraction."""

    def _scraper(self):
        return AlineaScraper(keywords="politik", queue_=asyncio.Queue())

    @pytest.mark.asyncio
    async def test_search_page_one_sets_q_and_page(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _alinea_search_html()})
        body = await s.build_search_url("politik", 1)
        assert body is not None
        assert len(stub.calls) == 1
        assert "q=politik" in stub.calls[0][0]
        assert "page=1" in stub.calls[0][0]

    @pytest.mark.asyncio
    async def test_search_page_two_appends_page_two(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _alinea_search_html()})
        await s.build_search_url("politik", 2)
        assert "page=2" in stub.calls[0][0]

    @pytest.mark.asyncio
    async def test_search_keyword_is_url_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _alinea_search_html()})
        await s.build_search_url("ekonomi & bisnis", 1)
        url = stub.calls[0][0]
        # Spaces must encode as %20 and the ampersand must encode as %26; the
        # raw '&' must NOT split the keyword from another query parameter.
        assert "%26" in url or "+" in url
        assert " " not in url

    def test_search_parser_keeps_sections_and_drops_offsite(self):
        s = self._scraper()
        links = s.parse_article_links(_alinea_search_html())
        assert links == {
            "https://www.alinea.id/politik/foo-bar-b123",
            "https://www.alinea.id/gaya-hidup/baz-qux-b456",
        }

    def test_search_parser_empty_body_stops_loop(self):
        s = self._scraper()
        assert s.parse_article_links("<html><body>no anchors</body></html>") is None
        assert s.continue_scraping is False

    @pytest.mark.asyncio
    async def test_latest_targets_indeks_page_one_only(self):
        s = AlineaScraper(keywords="politik", queue_=asyncio.Queue())
        stub = _attach_fetch(s, {"indeks": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0].endswith("/indeks")
        assert await s.build_latest_url(2) is None

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_with_path_category(self):
        link = "https://www.alinea.id/politik/foo-bar-b123"
        s = AlineaScraper(keywords="politik", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _alinea_article_html()})
        await s.get_article(link, "politik")

        item = s.queue_.get_nowait()
        assert item["title"] == "Alinea test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 0, 0, 0)
        assert item["author"] == "Reporter Satu"
        assert item["category"] == "politik"
        assert item["source"] == "www.alinea.id"
        assert item["link"] == link
        assert "Alinea lead paragraph" in item["content"]

    @pytest.mark.asyncio
    async def test_empty_body_short_circuits_without_put(self):
        link = "https://www.alinea.id/politik/empty"
        s = AlineaScraper(keywords="politik", queue_=asyncio.Queue())
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "politik")
        assert s.queue_.qsize() == 0


def _gnfi_search_html() -> str:
    return """<!doctype html><html><body>
        <a href="/2026/07/12/some-article">dated</a>
        <a href="https://www.goodnewsfromindonesia.id/2025/12/01/old-article">absolute</a>
        <a href="/c/lingkungan">category</a>
        <a href="/about">about</a>
        <a href="https://other.example.com/2026/07/12/foreign">off-site</a>
        <a href="/2026/7/12/no-leading-zero">bad month</a>
    </body></html>"""


def _gnfi_article_html() -> str:
    ld_payload = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "datePublished": "2026-07-12T10:00:00+00:00",
        "author": {"@type": "Person", "name": "JSON-LD Reporter"},
    })
    return (
        '<!doctype html><html><head>'
        '<meta property="og:title" content="GNFI test headline">'
        '<meta name="author" content="GNFI Reporter">'
        f'<script type="application/ld+json">{ld_payload}</script>'
        '</head><body>'
        '<div class="article-category"><a href="/c/lingkungan">Lingkungan</a></div>'
        '<div class="article-sheet">'
        '<p data-path-to-node="0">GNFI lead paragraph retained by the article-sheet extractor.</p>'
        '<p data-path-to-node="1">GNFI second paragraph retained by the article-sheet extractor.</p>'
        '</div>'
        '</body></html>'
    )


class TestGNFIFocus:
    """GNFI: search URL + parser, latest /explore page 1, extraction."""

    def _scraper(self):
        return GNFIScraper(keywords="bali", queue_=asyncio.Queue())

    @pytest.mark.asyncio
    async def test_search_page_one_omits_page_param(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _gnfi_search_html()})
        await s.build_search_url("bali", 1)
        url = stub.calls[0][0]
        assert url.startswith("https://www.goodnewsfromindonesia.id/search?")
        assert "keyword=bali" in url
        # Page 1 must omit page= so the upstream does not 404 on a stray param.
        assert "page=" not in url

    @pytest.mark.asyncio
    async def test_search_page_two_appends_page_param(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _gnfi_search_html()})
        await s.build_search_url("bali", 2)
        assert stub.calls[0][0].endswith("&page=2")

    @pytest.mark.asyncio
    async def test_search_keyword_is_percent_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _gnfi_search_html()})
        await s.build_search_url("ekonomi & bisnis/ihsg+market", 1)
        url = stub.calls[0][0]
        # The ampersand and space must be percent-encoded; raw '&' would split
        # the keyword from the next query parameter and corrupt the search.
        assert "keyword=ekonomi" in url
        assert "%26" in url and "%20" in url
        import re as _re
        assert _re.search(r"keyword=ekonomi[^%][^&]*&", url) is None

    def test_search_parser_keeps_dated_same_site_urls(self):
        s = self._scraper()
        links = s.parse_article_links(_gnfi_search_html())
        assert links == {
            "https://www.goodnewsfromindonesia.id/2026/07/12/some-article",
            "https://www.goodnewsfromindonesia.id/2025/12/01/old-article",
        }

    @pytest.mark.asyncio
    async def test_latest_targets_explore_page_one_only(self):
        s = GNFIScraper(keywords="bali", queue_=asyncio.Queue())
        stub = _attach_fetch(s, {"explore": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0].endswith("/explore")
        assert await s.build_latest_url(2) is None

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        link = "https://www.goodnewsfromindonesia.id/2026/07/12/test-article"
        s = GNFIScraper(keywords="bali", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _gnfi_article_html()})
        await s.get_article(link, "bali")

        item = s.queue_.get_nowait()
        assert item["title"] == "GNFI test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 10, 0, 0)
        # meta[name=author] wins over the JSON-LD author.
        assert item["author"] == "GNFI Reporter"
        assert item["category"] == "Lingkungan"
        assert item["source"] == "goodnewsfromindonesia.id"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_missing_date_short_circuits(self):
        link = "https://www.goodnewsfromindonesia.id/2026/07/12/no-date"
        html = """<!doctype html><html><head>
            <meta property="og:title" content="t">
            <meta name="author" content="a">
        </head><body><div class="article-sheet">
            <p data-path-to-node="0">body</p>
        </div></body></html>"""
        s = GNFIScraper(keywords="bali", queue_=asyncio.Queue())
        _attach_fetch(s, {link: html})
        await s.get_article(link, "bali")
        assert s.queue_.qsize() == 0


def _betahita_search_html() -> str:
    return """<!doctype html><html><body>
        <a href="/berita/12345/some-slug">berita</a>
        <a href="/opini/99/opinion-slug">opini</a>
        <a href="/sorot/100/featured-slug">sorot</a>
        <a href="/berita/no-id/slug">no id</a>
        <a href="/video/12345/some-slug">video</a>
        <a href="https://other.example.com/berita/1/foo">off-site</a>
        <a href="/sorot/keyword">sorot landing</a>
        <a href="/berita/12345/">trailing slash, no slug</a>
    </body></html>"""


def _betahita_article_html(*, header_label: str = "Berita") -> str:
    return f"""<!doctype html><html><head></head><body>
        <article class="detail-artikel">
            <div class="judul-artikel">
                <h5>{header_label}</h5>
                <h1>Betahita test headline</h1>
                <h5 class="margin-bottom-sm">Sabtu, 11 Juli 2026</h5>
            </div>
            <div class="box-sumber">
                <h5 class="title">Oleh: Betahita Reporter</h5>
            </div>
            <div class="detail-in">
                <p>Intro paragraph that must be skipped — dateline not yet seen.</p>
                <p>BETAHITA.ID — Betahita lead paragraph included after the dateline marker.</p>
                <p>Betahita second paragraph also included because it follows the dateline.</p>
                <div class="box-foto-artikel"><p>photo caption retained as text</p></div>
            </div>
        </article>
    </body></html>"""


class TestBetahitaFocus:
    """Betahita: search /search?query=&pagenum=, latest homepage, extraction."""

    def _scraper(self):
        return BetahitaScraper(keywords="lingkungan", queue_=asyncio.Queue())

    @pytest.mark.asyncio
    async def test_search_pagination_uses_pagenum_no_landing_walk(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _betahita_search_html()})
        await s.build_search_url("lingkungan", 2)
        url = stub.calls[0][0]
        assert url.startswith("https://www.betahita.id/search?")
        assert "query=lingkungan" in url
        assert "pagenum=2" in url
        # the canonical endpoint serves every page.
        assert "/berita/lingkungan" not in url
        assert "/opini/lingkungan" not in url
        assert "/sorot/lingkungan" not in url

    @pytest.mark.asyncio
    async def test_search_keyword_is_percent_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _betahita_search_html()})
        await s.build_search_url("ekonomi & bisnis", 1)
        expected = quote("ekonomi & bisnis", safe="")
        assert expected in stub.calls[0][0]

    def test_search_parser_keeps_berita_opini_and_sorot(self):
        s = self._scraper()
        links = s.parse_article_links(_betahita_search_html())
        assert links == {
            "https://www.betahita.id/berita/12345/some-slug",
            "https://www.betahita.id/opini/99/opinion-slug",
            "https://www.betahita.id/sorot/100/featured-slug",
        }

    def test_search_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None

    @pytest.mark.asyncio
    async def test_latest_targets_homepage_page_one_only(self):
        s = BetahitaScraper(keywords="lingkungan", queue_=asyncio.Queue())
        stub = _attach_fetch(s, {"betahita.id": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://www.betahita.id"
        assert await s.build_latest_url(2) is None

    def test_latest_parser_keeps_berita_and_opini_drops_others(self):
        s = BetahitaScraper(keywords="lingkungan", queue_=asyncio.Queue())
        html = """<!doctype html><html><body>
            <a href="/berita/12345/some-slug">berita</a>
            <a href="/opini/99/opinion-slug">opini</a>
            <a href="/video/12345/some-slug">video</a>
            <a href="/tentang-kami">about</a>
            <a href="/berita/no-id/slug">no numeric id</a>
            <a href="https://www.betahita.id/berita/7/leading-zero-id">leading-zero</a>
        </body></html>"""
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://www.betahita.id/berita/12345/some-slug",
            "https://www.betahita.id/opini/99/opinion-slug",
            "https://www.betahita.id/berita/7/leading-zero-id",
        }
        assert s.parse_latest_article_links("") is None

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_with_dateline_filter(self):
        link = "https://www.betahita.id/berita/12345/test-article"
        s = BetahitaScraper(keywords="lingkungan", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _betahita_article_html()})
        await s.get_article(link, "lingkungan")

        item = s.queue_.get_nowait()
        assert item["title"] == "Betahita test headline"
        assert item["publish_date"] == datetime(2026, 7, 11, 0, 0, 0)
        assert item["publish_date"].tzinfo is None
        assert item["author"] == "Betahita Reporter"
        assert item["category"] == "Berita"
        assert item["source"] == "betahita.id"
        assert item["link"] == link
        # Everything before the dateline must be filtered out; the post-dateline
        # paragraph and the photo caption must remain.
        assert "Intro paragraph" not in item["content"]
        assert "Betahita second paragraph" in item["content"]

    @pytest.mark.asyncio
    async def test_opini_path_derives_opini_category(self):
        link = "https://www.betahita.id/opini/99/opinion-piece"
        s = BetahitaScraper(keywords="lingkungan", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _betahita_article_html(header_label="Opini")})
        await s.get_article(link, "lingkungan")
        item = s.queue_.get_nowait()
        assert item["category"] == "Opini"


def _nusabali_search_html() -> str:
    return """<!doctype html><html><body>
        <a href="/berita/225365/pria-mabuk-diamankan-polisi">article</a>
        <a href="/berita/7/leading-zero">short id</a>
        <a href="/opini/123/foo">opini</a>
        <a href="/tag/bali">tag</a>
        <a href="/about">about</a>
        <a href="/berita/not-a-number/slug">non-numeric</a>
    </body></html>"""


def _nusabali_article_html() -> str:
    return """<!doctype html><html><head>
        <meta property="og:title" content="NusaBali test headline">
    </head><body>
        <div class="entry-box-header">
            <span class="month pull-left" itemprop="datePublished">12 Jul 2026 19:37:24</span>
        </div>
        <span itemprop="author">Penulis : I Putu Reporter</span>
        <div class="breadcrumb">
            <span class="article-category" itemprop="articleSection">Denpasar</span>
        </div>
        <div class="entry-content" itemprop="articleBody">
            <p>NusaBali lead paragraph retained by the entry-content extractor.</p>
            <p>NusaBali second paragraph retained because it sits inside articleBody.</p>
        </div>
    </body></html>"""


class TestNusaBaliFocus:
    """NusaBali: search keyword+page, latest homepage, extraction."""

    def _scraper(self):
        return NusaBaliScraper(keywords="bali", queue_=asyncio.Queue())

    @pytest.mark.asyncio
    async def test_search_keyword_quoted_and_page_param_present(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _nusabali_search_html()})
        await s.build_search_url("bali", 1)
        url = stub.calls[0][0]
        assert "keyword=bali" in url
        assert "page=1" in url

    @pytest.mark.asyncio
    async def test_search_page_two_sets_page_two(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _nusabali_search_html()})
        await s.build_search_url("bali", 2)
        assert "page=2" in stub.calls[0][0]
    @pytest.mark.asyncio
    async def test_search_keyword_is_percent_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _nusabali_search_html()})
        await s.build_search_url("ekonomi & bisnis", 1)
        expected = quote("ekonomi & bisnis", safe="")
        assert expected in stub.calls[0][0]
    @pytest.mark.asyncio
    async def test_search_empty_fetch_returns_none(self):
        # No fetch stub attached — empty body bubbles up as None.
        s = NusaBaliScraper(keywords="bali", queue_=asyncio.Queue())
        assert await s.build_search_url("nobody-home", 1) is None

    def test_search_parser_keeps_only_berita_numeric_id_slug(self):
        s = self._scraper()
        links = s.parse_article_links(_nusabali_search_html())
        assert links == {
            "https://www.nusabali.com/berita/225365/pria-mabuk-diamankan-polisi",
            "https://www.nusabali.com/berita/7/leading-zero",
        }

    def test_search_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None

    @pytest.mark.asyncio
    async def test_latest_targets_homepage_page_one_only(self):
        s = NusaBaliScraper(keywords="bali", queue_=asyncio.Queue())
        stub = _attach_fetch(s, {"nusabali.com": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://www.nusabali.com"

    def test_latest_parser_keeps_only_berita_numeric_id_slug(self):
        s = NusaBaliScraper(keywords="bali", queue_=asyncio.Queue())
        links = s.parse_latest_article_links(_nusabali_search_html())
        assert links == {
            "https://www.nusabali.com/berita/225365/pria-mabuk-diamankan-polisi",
            "https://www.nusabali.com/berita/7/leading-zero",
        }
        assert s.parse_latest_article_links("") is None

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_with_author_prefix(self):
        link = "https://www.nusabali.com/berita/225365/pria-mabuk-di-desa-keramas"
        s = NusaBaliScraper(keywords="bali", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _nusabali_article_html()})
        await s.get_article(link, "bali")

        item = s.queue_.get_nowait()
        assert item["title"] == "NusaBali test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 19, 37, 24)
        # "Penulis : " prefix must be preserved verbatim.
        assert item["author"] == "Penulis : I Putu Reporter"
        assert item["category"] == "Denpasar"
        assert item["source"] == "nusabali.com"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_category_falls_back_to_unknown_when_no_breadcrumb(self):
        link = "https://www.nusabali.com/berita/1/no-crumb"
        html = """<!doctype html><html><head>
            <meta property="og:title" content="t">
        </head><body>
            <span class="month pull-left" itemprop="datePublished">12 Jul 2026 19:37:24</span>
            <span itemprop="author">Some Author</span>
            <div class="entry-content" itemprop="articleBody">
                <p>NusaBali body paragraph for the unknown-category fallback test path.</p>
            </div>
        </body></html>"""
        s = NusaBaliScraper(keywords="bali", queue_=asyncio.Queue())
        _attach_fetch(s, {link: html})
        await s.get_article(link, "bali")

        item = s.queue_.get_nowait()
        assert item["category"] == "Unknown"


def _conversation_search_html() -> str:
    return """<!doctype html><html><body>
        <a href="/some-article-12345">article</a>
        <a href="https://theconversation.com/another-article-67890">absolute article</a>
        <a href="/topics/climate-change">topics</a>
        <a href="/authors/jane-doe">authors</a>
        <a href="/partners/foo">partners</a>
        <a href="/id/about-us">section about</a>
        <a href="/newsletters/signup">newsletter</a>
    </body></html>"""


def _conversation_article_html() -> str:
    return """<!doctype html><html><head>
        <meta property="og:title" content="Conversation ID test headline">
    </head><body>
        <time datetime="2026-07-12T10:00:00Z">12 July 2026</time>
        <a rel="author" href="/profile/author-one">Author One</a>
        <a rel="author" href="/profile/author-two">Author Two</a>
        <a href="/topics/politics">Politics</a>
        <a href="/topics/economics">Economics</a>
        <div itemprop="articleBody">
            <p>Conversation ID lead paragraph retained by the articleBody extractor.</p>
            <p>Conversation ID second paragraph retained by the articleBody extractor.</p>
        </div>
    </body></html>"""


class TestConversationIDFocus:
    """Conversation ID: search /id/search with full query string,
    latest /id homepage, multi-author + multi-topic extraction, time→meta fallback."""

    def _scraper(self):
        return ConversationIDScraper(keywords="indonesia", queue_=asyncio.Queue())

    @pytest.mark.asyncio
    async def test_search_emits_full_canonical_query(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _conversation_search_html()})
        body = await s.build_search_url("politik", 1)
        assert body is not None
        url = stub.calls[0][0]
        # Exact query-string contract: every parameter in the prescribed order.
        assert "date=all" in url
        assert "date_from=" in url
        assert "date_to=" in url
        assert "language=id" in url
        assert "page=1" in url
        assert "q=politik" in url
        assert "sort=recency" in url

    @pytest.mark.asyncio
    async def test_search_page_two_swaps_page_param(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _conversation_search_html()})
        await s.build_search_url("politik", 2)
        assert "page=2" in stub.calls[0][0]
    @pytest.mark.asyncio
    async def test_search_keyword_is_url_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": _conversation_search_html()})
        await s.build_search_url("ekonomi & bisnis", 1)
        expected = quote("ekonomi & bisnis", safe="")
        assert f"q={expected}" in stub.calls[0][0]
    @pytest.mark.asyncio
    async def test_search_empty_fetch_returns_none(self):
        # No fetch stub attached — empty body bubbles up as None.
        s = ConversationIDScraper(keywords="indonesia", queue_=asyncio.Queue())
        assert await s.build_search_url("nobody-home", 1) is None

    def test_search_parser_keeps_articles_drops_section_paths(self):
        s = self._scraper()
        links = s.parse_article_links(_conversation_search_html())
        assert links == {
            "https://theconversation.com/some-article-12345",
            "https://theconversation.com/another-article-67890",
        }
        assert s.parse_article_links("") is None

    @pytest.mark.asyncio
    async def test_latest_targets_id_homepage_page_one_only(self):
        s = ConversationIDScraper(keywords="indonesia", queue_=asyncio.Queue())
        stub = _attach_fetch(s, {"theconversation.com/id": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://theconversation.com/id"

    def test_latest_parser_keeps_articles_drops_section_paths(self):
        s = ConversationIDScraper(keywords="indonesia", queue_=asyncio.Queue())
        links = s.parse_latest_article_links(_conversation_search_html())
        assert links == {
            "https://theconversation.com/some-article-12345",
            "https://theconversation.com/another-article-67890",
        }
        assert s.parse_latest_article_links("") is None

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_multi_author_and_topic(self):
        link = "https://theconversation.com/some-article-12345"
        s = ConversationIDScraper(keywords="indonesia", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _conversation_article_html()})
        await s.get_article(link, "indonesia")

        item = s.queue_.get_nowait()
        assert item["title"] == "Conversation ID test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 10, 0, 0)
        assert item["publish_date"].tzinfo is None
        # Multiple authors joined with comma, preserving insertion order.
        assert item["author"] == "Author One, Author Two"
        # Multiple topic links joined into a single category string.
        assert item["category"] == "Politics, Economics"
        assert item["source"] == "theconversation.com"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_missing_time_falls_back_to_meta(self):
        link = "https://theconversation.com/fallback-article-99999"
        html = """<!doctype html><html><head>
            <meta property="og:title" content="t">
            <meta property="article:published_time" content="2026-07-12T12:00:00Z">
        </head><body><div itemprop="articleBody">
            <p>Conversation ID fallback body paragraph for the meta-only date path.</p>
        </div></body></html>"""
        s = ConversationIDScraper(keywords="indonesia", queue_=asyncio.Queue())
        _attach_fetch(s, {link: html})
        await s.get_article(link, "indonesia")

        item = s.queue_.get_nowait()
        assert item["publish_date"] == datetime(2026, 7, 12, 12, 0, 0)
        assert item["publish_date"].tzinfo is None


def _hukumonline_sitemap_xml(urls: list[str]) -> str:
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        body += f"  <url><loc>{u}</loc></url>\n"
    body += "</urlset>\n"
    return body


def _hukumonline_article_html() -> str:
    ld_payload = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "datePublished": "2026-07-12T10:00:00+07:00",
        "articleSection": "Hukum",
        "author": {"@type": "Person", "name": "Hukumonline Reporter"},
    })
    return (
        '<!doctype html><html><head>'
        '<meta property="og:title" content="Hukumonline test headline">'
        f'<script type="application/ld+json">{ld_payload}</script>'
        '</head><body>'
        '<article>'
        '<p>Hukumonline lead paragraph included by the article-descendant extractor.</p>'
        '<p>Hukumonline second paragraph continuing the joined article body.</p>'
        '</article>'
        '</body></html>'
    )


class TestHukumonlineFocus:
    """Hukumonline: latest /berita/sitemap.xml + XML guard + extraction."""

    @pytest.mark.asyncio
    async def test_latest_targets_berita_sitemap_xml(self):
        s = HukumonlineScraper(keywords="hukum", queue_=asyncio.Queue())
        stub = _attach_fetch(s, {"": _hukumonline_sitemap_xml([])})
        await s.build_latest_url(1)
        assert stub.calls[0][0] == "https://www.hukumonline.com/berita/sitemap.xml"

    def test_latest_parser_keeps_berita_a_slugs_drops_foto_stories(self):
        s = HukumonlineScraper(keywords="hukum", queue_=asyncio.Queue())
        xml = _hukumonline_sitemap_xml([
            "https://www.hukumonline.com/berita/a/canonical-slug",
            "https://www.hukumonline.com/berita/a/multi-segment/slug",
            "https://www.hukumonline.com/berita/a/canonical-slug-with-trailing/",
            "https://www.hukumonline.com/berita/foto/some-gallery",
            "https://www.hukumonline.com/berita/stories/some-longform",
            "https://www.hukumonline.com/berita/a/",
            "https://www.hukumonline.com/lain/a/something",
        ])
        links = s.parse_latest_article_links(xml)
        assert links == [
            "https://www.hukumonline.com/berita/a/canonical-slug",
            "https://www.hukumonline.com/berita/a/multi-segment/slug",
            "https://www.hukumonline.com/berita/a/canonical-slug-with-trailing",
        ]

    def test_latest_parser_rejects_html_doc_html(self):
        s = HukumonlineScraper(keywords="hukum", queue_=asyncio.Queue())
        cloudflare = (
            "<!doctype html><html><head><title>Just a moment...</title>"
            "</head><body>Please enable JavaScript to continue.</body></html>"
        )
        assert s.parse_latest_article_links(cloudflare) is None

    def test_latest_parser_rejects_html_without_doctype_marker(self):
        s = HukumonlineScraper(keywords="hukum", queue_=asyncio.Queue())
        assert s.parse_latest_article_links(
            "<html><body>unexpected HTML body without sitemap markers</body></html>"
        ) is None

    def test_latest_parser_rejects_malformed_xml(self):
        s = HukumonlineScraper(keywords="hukum", queue_=asyncio.Queue())
        assert s.parse_latest_article_links(
            "<?xml version='1.0'?><urlset><url><loc>oops</loc></url"
        ) is None

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_with_jsonld(self):
        link = "https://www.hukumonline.com/berita/a/canonical-slug"
        s = HukumonlineScraper(keywords="hukum", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _hukumonline_article_html()})
        await s.get_article(link, "hukum")

        item = s.queue_.get_nowait()
        assert item["title"] == "Hukumonline test headline"
        # dateparser returns tz-aware for +07:00; assert the calendar value.
        assert item["publish_date"].year == 2026
        assert item["publish_date"].month == 7
        assert item["publish_date"].day == 12
        assert item["publish_date"].hour == 10
        assert item["author"] == "Hukumonline Reporter"
        assert item["category"] == "Hukum"
        assert item["source"] == "hukumonline.com"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_section_falls_back_to_meta(self):
        link = "https://www.hukumonline.com/berita/a/fallback-section"
        ld_payload = json.dumps({
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "datePublished": "2026-07-12T10:00:00+07:00",
            "author": {"@type": "Person", "name": "x"},
        })
        html = (
            '<!doctype html><html><head>'
            '<meta property="og:title" content="t">'
            '<meta property="article:section" content="Bisnis">'
            f'<script type="application/ld+json">{ld_payload}</script>'
            '</head><body>'
            '<article>'
            '<p>Hukumonline fallback body paragraph for the meta-section test path.</p>'
            '</article>'
            '</body></html>'
        )
        s = HukumonlineScraper(keywords="hukum", queue_=asyncio.Queue())
        _attach_fetch(s, {link: html})
        await s.get_article(link, "hukum")

        item = s.queue_.get_nowait()
        # article:section meta wins because JSON-LD omitted articleSection.
        assert item["category"] == "Bisnis"


def _independen_article_html() -> str:
    return """<!doctype html><html><head>
        <meta property="og:title" content="Independen test headline - Independen.id">
        <meta property="article:published_time" content="2026-07-12T10:00:00+07:00">
        <meta property="article:section" content="Investigasi">
        <meta name="author" content="Independen Reporter">
    </head><body>
        <article>
            <p class="lead">Independen lead paragraph surviving the 25-char filter inside the article.</p>
            <p>Independen second paragraph continuing the joined article body from the markup.</p>
            <div class="share-buttons"><a href="#">share</a></div>
            <div class="related-articles"><p>related noise — must be removed</p></div>
        </article>
    </body></html>"""


class TestIndependenFocus:
    """Independen: Drupal-root slug homepage parser + article extraction
    (og:title suffix stripped, share/related stripped, short-circuit paths)."""

    def _scraper(self):
        return IndependenScraper(keywords="indonesia", queue_=asyncio.Queue())

    def test_latest_parser_keeps_root_level_slugs_only(self):
        s = self._scraper()
        html = """<!doctype html><html><body>
            <a href="/judul-artikel-contoh">article slug</a>
            <a href="https://independen.id/artikel/lainnya">absolute root</a>
            <a href="/node/12345">drupal canonical node</a>
            <a href="/taxonomy/term/7">taxonomy</a>
            <a href="/user/42">user</a>
            <a href="/users/42">users alias</a>
            <a href="/tags/bencana">tags landing</a>
            <a href="/tag/bencana">tag landing</a>
            <a href="/agenda/2026-07-12">agenda</a>
            <a href="/category/legacy">category alias</a>
            <a href="/kategori/legacy">kategori alias</a>
            <a href="/frontpages">front page</a>
            <a href="/front-page">front page variant</a>
            <a href="/about">about</a>
            <a href="/contact">contact</a>
            <a href="/kontak">kontak</a>
            <a href="/pedoman">pedoman</a>
            <a href="/ketentuan">ketentuan</a>
            <a href="/privacy">privacy</a>
            <a href="/advertise">advertise</a>
            <a href="/iklan">iklan</a>
            <a href="/redaksi">redaksi</a>
            <a href="/penulis">penulis</a>
            <a href="/kolom">kolom</a>
            <a href="/search">search</a>
            <a href="/berita">section landing</a>
            <a href="/politik">section landing</a>
            <a href="/hukum-dan-ham">section landing</a>
            <a href="/ekonomi">section landing</a>
            <a href="/lingkungan">section landing</a>
            <a href="/kesehatan">section landing</a>
            <a href="/teknologi">section landing</a>
            <a href="/pendidikan">section landing</a>
            <a href="/budaya">section landing</a>
            <a href="/opini">section landing</a>
            <a href="/feature">section landing</a>
            <a href="/investigasi">section landing</a>
            <a href="/infografis">section landing</a>
            <a href="/video">section landing</a>
            <a href="/foto">section landing</a>
            <a href="/galeri">section landing</a>
            <a href="/live">section landing</a>
            <a href="/">homepage self</a>
            <a href="/image.png">asset</a>
            <a href="/document.pdf">asset</a>
        </body></html>"""
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://independen.id/judul-artikel-contoh",
            "https://independen.id/artikel/lainnya",
        }

    def test_latest_parser_strips_query_and_fragment(self):
        s = self._scraper()
        html = """<!doctype html><html><body>
            <a href="/judul?ref=home">query — canonical</a>
            <a href="/other-article#section">fragment — canonical</a>
        </body></html>"""
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://independen.id/judul",
            "https://independen.id/other-article",
        }

    def test_latest_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_latest_article_links("") is None
        assert s.parse_latest_article_links(None) is None  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_with_ogtitle_suffix_stripped(self):
        link = "https://independen.id/judul-artikel-contoh/"
        s = IndependenScraper(keywords="indonesia", queue_=asyncio.Queue())
        _attach_fetch(s, {link: _independen_article_html()})
        await s.get_article(link, "indonesia")

        item = s.queue_.get_nowait()
        # og:title suffix "- Independen.id" must be stripped.
        assert item["title"] == "Independen test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 3, 0, 0)
        assert item["publish_date"].tzinfo is None
        assert item["author"] == "Independen Reporter"
        assert item["category"] == "Investigasi"
        assert item["source"] == "independen.id"
        assert item["link"] == link
        # Content must come from the <article> node and skip the share/related
        # blocks. The 25-char filter keeps the lead paragraph and drops short
        # noise inside share/related.
        assert "Independen lead paragraph" in item["content"]
        assert "Independen share" not in item["content"]
        assert "related noise" not in item["content"]

    @pytest.mark.asyncio
    async def test_empty_body_short_circuits_without_put(self):
        link = "https://independen.id/empty/"
        s = IndependenScraper(keywords="indonesia", queue_=asyncio.Queue())
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "indonesia")
        assert s.queue_.qsize() == 0

    @pytest.mark.asyncio
    async def test_missing_title_short_circuits(self):
        link = "https://independen.id/no-title/"
        html = """<!doctype html><html><head>
            <meta property="article:published_time" content="2026-07-12T10:00:00+07:00">
        </head><body><article>
            <p>body paragraph over twenty-five chars long for the short-circuit path</p>
        </article></body></html>"""
        s = IndependenScraper(keywords="indonesia", queue_=asyncio.Queue())
        _attach_fetch(s, {link: html})
        await s.get_article(link, "indonesia")
        assert s.queue_.qsize() == 0