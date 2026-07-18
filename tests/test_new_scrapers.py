"""Deterministic offline contract tests for the three newest adapters.

Finalized slugs (per project assignment):
    ddtcnews        — Playwright search, server-rendered article pages,
                       ID-locale date, meta-name author, meta-name category
    idnfinancials   — server-rendered /id/search?q= with Berita-widget
                       relevance filter, NO_RESULT_MARKER gate, meta+JSON-LD
                       date, JSON-LD author, article:section category
    wartaekonomi    — POST /search with redirect-token pagination,
                       _current_keyword-aware relevance filter, JSON-LD/meta
                       date, JSON-LD author, JSON-LD/breadcrumb category,
                       canonical link extraction, dated /indeks/YYYYMMDD
                       archive driven by start_date

Tests pin:
- discovery contracts per adapter (URL building, page param, search-id
  capture for Warta Ekonomi, NO_RESULT_MARKER gate for IDN Financials,
  Berita-only widget selection, regex acceptance/rejection, empty/no-result
  paths);
- article extraction contracts (title, publish_date, author, content,
  category) — including Warta Ekonomi canonical-link resolution and IDN
  Financials JSON-LD author / article:section category;
- start_date cutoff behavior (article dropped and continue_scraping=False)
  for all three adapters;
- exact queue schema (title, publish_date, author, content, keyword,
  category, source, link) across all three adapters;
- Warta Ekonomi lower-date archive URL contract: start_date drives the
  /indeks/YYYYMMDD token, not /indeks?page=N.

fetch() is stubbed in-process; no HTTP is performed.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from datetime import datetime
from typing import Any

import pytest

from newswatch.registry import SCRAPERS


# ── Registry-derived helpers ───────────────────────────────────────────────


_NEW_SLUGS: tuple[str, ...] = ("ddtcnews", "idnfinancials", "wartaekonomi")


def _scraper_class(slug: str) -> type:
    entry = SCRAPERS[slug]
    module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
    return getattr(module, entry.class_name)


# ── Fetch stub ─────────────────────────────────────────────────────────────


class _FetchStub:
    """Replace ``scraper.fetch`` with a URL-substring → body lookup.

    Returns the matched body for any URL containing one of the registered
    substrings; returns ``None`` otherwise so callers that key on falsy
    responses (e.g. IDN Financials' "no article" path) observe the same
    fall-through they would in production.
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


# ── Queue schema (the contract) ─────────────────────────────────────────────


_QUEUE_KEYS: tuple[str, ...] = (
    "title", "publish_date", "author", "content",
    "keyword", "category", "source", "link",
)


# ── DDTC News fixtures ──────────────────────────────────────────────────────


def _ddtc_article_html(*, date_text: str = "Minggu, 12 Juli 2026") -> str:
    return f"""<!doctype html>
<html><head>
<meta property="og:title" content="DDTC test headline">
</head><body>
<h1>DDTC test headline</h1>
<div id="publish-news">{date_text}</div>
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


def _ddtc_search_html() -> str:
    return """<!doctype html>
<html><body>
  <div class="news-item"><a href="/berita/foo-bar/123/some-slug">some-slug</a></div>
  <div class="news-item"><a href="/review/tax/456/another-slug">another-slug</a></div>
  <div class="news-item"><a href="/literasi/edu/789/third-slug">third-slug</a></div>
  <div class="news-item"><a href="/komunitas/forum/101/fourth-slug">fourth-slug</a></div>
  <div class="news-item"><a href="/news/something/202/wrong-section">wrong-section</a></div>
  <div class="news-item"><a href="/berita/2026">missing-slug-and-id</a></div>
  <div class="news-item"><a href="https://other.example.com/berita/x/9/y">offsite</a></div>
</body></html>
"""


# ── IDN Financials fixtures ────────────────────────────────────────────────


def _idn_berita_widget_html(
    *,
    items: list[dict[str, str]],
    extra_video_widget: bool = True,
) -> str:
    """Render the .widget.side-news region with both Berita and Video widgets.

    Each item must include ``href`` and ``title``. The Video widget must be
    dropped because the parser only accepts widgets whose header is exactly
    "berita".
    """
    berita_items = "\n".join(
        f'<li class="item"><a href="{it["href"]}" title="{it["title"]}">{it["title"]}</a></li>'
        for it in items
    )
    video_items = (
        '<li class="item"><a href="/id/news/999999/video-slug" '
        'title="Unrelated video title">video</a></li>'
    )
    video_widget = (
        f'<div class="widget side-news"><div class="widget-header">'
        f'<h2>Video</h2></div><div class="widget-body">'
        f'<ul class="list">{video_items}</ul></div></div>'
        if extra_video_widget
        else ""
    )
    return f"""<!doctype html>
<html><body>
<div class="widget side-news">
  <div class="widget-header"><h2>Berita</h2></div>
  <div class="widget-body">
    <ul class="list">{berita_items}</ul>
  </div>
</div>
{video_widget}
</body></html>
"""


def _idn_no_result_html() -> str:
    return """<!doctype html>
<html><body>
<blockquote>Tidak ada data yang ditemukan</blockquote>
</body></html>
"""


def _idn_article_html(
    *,
    title: str = "IDN Financials test headline",
    published_time: str = "2026-07-12T10:00:00+07:00",
    author_name: str = "IDN Financials Reporter",
    section: str = "Berita",
    body_paragraphs: tuple[str, ...] = (
        "IDN Financials lead paragraph that the article-body extractor pulls.",
        "IDN Financials second paragraph retained by the body extractor.",
    ),
) -> str:
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
    paragraphs = "\n".join(f"<p>{p}</p>" for p in body_paragraphs)
    return (
        '<!doctype html>\n<html><head>\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="article:section" content="{section}">\n'
        f'<script type="application/ld+json">\n{ld_payload}\n</script>\n'
        '</head><body>\n'
        f'<div class="article-body">{paragraphs}</div>\n'
        '</body></html>\n'
    )


# ── Warta Ekonomi fixtures ──────────────────────────────────────────────────


def _warta_search_html(*, article_hrefs: list[dict[str, str]], search_id: str = "42") -> str:
    """Render a Warta Ekonomi search-results page.

    Each entry needs ``href``, ``title``, and ``class="articleListItem"``.
    Includes a pagination anchor so ``parse_article_links`` captures the
    ``_search_id`` for subsequent pages.
    """
    items = "\n".join(
        f'<a class="articleListItem" href="{a["href"]}" title="{a["title"]}">{a["title"]}</a>'
        for a in article_hrefs
    )
    return f"""<!doctype html>
<html><body>
<div class="article-list">
{items}
</div>
<div class="pagination">
  <a href="/search/{search_id}?page=2">next</a>
</div>
</body></html>
"""


def _warta_article_html(
    *,
    title: str = "Warta Ekonomi test headline",
    canonical: str = "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline",
    section: str = "Makro",
    author_name: str = "Warta Ekonomi Reporter",
    published_time: str = "2026-07-12T10:00:00+07:00",
    body_paragraphs: tuple[str, ...] = (
        "Warta Ekonomi lead paragraph retained by the articlePostContent extractor.",
        "Warta Ekonomi second paragraph continuing the article body.",
        # Inline cross-promo anchor inside the body — the extractor must
        # decompose it because the anchor's text starts with "Baca Juga".
        '<a href="/read99999/unrelated-promo">Baca Juga: cross promo link</a> kept',
        # Noise-class container with another promo anchor — must be stripped
        # because its CSS class matches the noise regex.
        '<div class="baca-juga-box"><a href="/x">must be removed</a></div>',
    ),
    include_canonical: bool = True,
) -> str:
    ld_payload = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "datePublished": published_time,
        "author": {"@type": "Person", "name": author_name},
        "articleSection": section,
    })
    paragraphs = "\n".join(f"<p>{p}</p>" for p in body_paragraphs)
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
        f'<div class="articlePostContent">{paragraphs}</div>\n'
        '</article>\n'
        '</body></html>\n'
    )


def _warta_indeks_html() -> str:
    return """<!doctype html>
<html><body>
<a class="articleListItem" href="/read33333/indeks-article-one" title="Indeks article one">indeks-article-one</a>
<a class="articleListItem" href="/read44444/indeks-article-two" title="Indeks article two">indeks-article-two</a>
<a href="/category/foo">category — must be dropped</a>
<a href="https://other.example.com/read55555/off-site">off-site — must be dropped</a>
</body></html>
"""


# ── DDTC News — discovery ──────────────────────────────────────────────────


class TestDDTCNewsSearchURLFiltering:
    """DDTC News search-mode parser accepts the four article sections only.

    The Playwright-driven ``fetch_search_results`` flow is not exercised here;
    the contract under test is the synchronous ``parse_article_links`` against
    the rendered HTML, plus the deliberate ``build_search_url -> None`` stub.
    """

    def _scraper(self):
        return _scraper_class("ddtcnews")(
            keywords="pajak",
            queue_=asyncio.Queue(),
        )

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
        links = s.parse_article_links(_ddtc_search_html())
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
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"news.ddtc.co.id": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://news.ddtc.co.id"

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(2) is None

    def test_latest_parser_keeps_article_sections_drops_others(self):
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
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
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None
        assert s.parse_latest_article_links(None) is None  # type: ignore[arg-type]


# ── DDTC News — extraction ─────────────────────────────────────────────────


class TestDDTCNewsGetArticle:
    """DDTC News article extraction contract: og:title, #publish-news date,
    div.contentArticle body with script/iframe stripping, meta author and
    meta category fallbacks."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
        link = "https://news.ddtc.co.id/berita/foo-bar/123/test-article"
        _attach_fetch(s, {link: _ddtc_article_html()})
        await s.get_article(link, "pajak")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
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
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
        link = "https://news.ddtc.co.id/berita/empty/999/x"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "pajak")
        assert s.queue_.qsize() == 0

    @pytest.mark.asyncio
    async def test_missing_publish_date_short_circuits(self):
        """Without #publish-news, the date parser must skip the article — the
        queue must stay empty."""
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
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


# ── DDTC News — queue schema ───────────────────────────────────────────────


class TestDDTCNewsQueueSchema:
    """DDTC News queue items must contain exactly the eight contract keys
    with the expected types, and source must be the canonical domain."""

    @pytest.mark.asyncio
    async def test_get_article_emits_exact_queue_schema(self):
        s = _scraper_class("ddtcnews")(
            keywords="pajak", queue_=asyncio.Queue(),
        )
        link = "https://news.ddtc.co.id/berita/foo-bar/123/test-article"
        _attach_fetch(s, {link: _ddtc_article_html()})
        await s.get_article(link, "pajak")

        assert s.queue_.qsize() == 1
        item = s.queue_.get_nowait()
        assert tuple(sorted(item)) == tuple(sorted(_QUEUE_KEYS))
        assert isinstance(item["publish_date"], datetime)
        assert isinstance(item["title"], str) and item["title"]
        assert isinstance(item["author"], str) and item["author"]
        assert isinstance(item["content"], str) and item["content"]
        assert item["keyword"] == "pajak"
        assert isinstance(item["category"], str) and item["category"]
        assert isinstance(item["source"], str) and item["source"]
        assert item["link"] == link


# ── DDTC News — cutoff ─────────────────────────────────────────────────────


class TestDDTCNewsCutoff:
    """start_date in the future must drop the article and flip
    continue_scraping — the queue stays empty."""

    @pytest.mark.asyncio
    async def test_start_date_in_future_drops_article_and_flips_flag(self):
        s = _scraper_class("ddtcnews")(
            keywords="pajak",
            start_date=datetime(2099, 1, 1),
            queue_=asyncio.Queue(),
        )
        link = "https://news.ddtc.co.id/berita/foo-bar/123/test-article"
        _attach_fetch(s, {link: _ddtc_article_html()})
        await s.get_article(link, "pajak")
        assert s.queue_.qsize() == 0
        assert s.continue_scraping is False


# ── IDN Financials — discovery ──────────────────────────────────────────────


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
        return _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
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
        stub = _attach_fetch(s, {"/id/search": _idn_no_result_html()})
        result = await s.build_search_url("makan", 1)
        assert result is not None  # the body was served
        assert s.parse_article_links(result) is None
        assert s.continue_scraping is False
        # The body was served once and then the parser rejected it; no further
        # fetch was attempted.
        assert len(stub.calls) == 1

    def test_parser_keeps_berita_widget_drops_video_widget(self):
        s = self._scraper()
        html = _idn_berita_widget_html(
            items=[
            {"href": "/id/news/123/berita-makan-bergizi-gratis", "title": "Makan Bergizi Gratis Article"},
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
        html = _idn_berita_widget_html(
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
        html = _idn_berita_widget_html(
            items=[
                {"href": "/id/news/1/relevant-makan-bergizi-gratis", "title": "Makan Bergizi Gratis Headline"},
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
        html = _idn_berita_widget_html(
            items=[
                {"href": "/id/news/200/badan-gizi-launch", "title": "Badan Gizi Launch"},
                {"href": "/id/news/201/badan-gizi-nasional-resmi", "title": "Badan Gizi Nasional Resmi Dibentuk"},
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
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/id/news": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://www.idnfinancials.com/id/news"

    @pytest.mark.asyncio
    async def test_page_two_adds_page_param(self):
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/id/news": "<html></html>"})
        await s.build_latest_url(2)
        assert stub.calls[0][0] == "https://www.idnfinancials.com/id/news?page=2"

    @pytest.mark.asyncio
    async def test_outside_max_pages_returns_none(self):
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(0) is None
        assert await s.build_latest_url(999) is None

    def test_latest_parser_keeps_article_urls_only(self):
        s = _scraper_class("idnfinancials")(
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
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None


# ── IDN Financials — extraction ─────────────────────────────────────────────


class TestIDNFinancialsGetArticle:
    """IDN Financials article extraction contract: og:title (or h2.title /
    h1 fallback), authoritative meta + JSON-LD date with a final data-date
    fallback, JSON-LD author with meta and header-card fallbacks,
    article:section category with URL-based "Berita" fallback, body via
    div.article-body (article fallback)."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item_from_jsonld(self):
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/123/test-article"
        _attach_fetch(s, {link: _idn_article_html()})
        await s.get_article(link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
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
    async def test_falls_back_to_meta_published_time_when_jsonld_missing(self):
        """article:published_time meta tag is the authoritative first try."""
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
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
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
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
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/111/empty"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "makan bergizi gratis")
        assert s.queue_.qsize() == 0


# ── IDN Financials — queue schema ──────────────────────────────────────────


class TestIDNFinancialsQueueSchema:
    """IDN Financials queue items must contain exactly the eight contract
    keys with the expected types; source must be the canonical domain."""

    @pytest.mark.asyncio
    async def test_get_article_emits_exact_queue_schema(self):
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/123/test-article"
        _attach_fetch(s, {link: _idn_article_html()})
        await s.get_article(link, "makan bergizi gratis")

        assert s.queue_.qsize() == 1
        item = s.queue_.get_nowait()
        assert tuple(sorted(item)) == tuple(sorted(_QUEUE_KEYS))
        assert isinstance(item["publish_date"], datetime)
        assert isinstance(item["title"], str) and item["title"]
        assert isinstance(item["author"], str) and item["author"]
        assert isinstance(item["content"], str) and item["content"]
        assert item["keyword"] == "makan bergizi gratis"
        assert isinstance(item["category"], str) and item["category"]
        assert isinstance(item["source"], str) and item["source"]
        assert item["link"] == link
        assert item["source"] == "idnfinancials.com"


# ── IDN Financials — cutoff ────────────────────────────────────────────────


class TestIDNFinancialsCutoff:
    """start_date in the future must drop the article and flip
    continue_scraping — the queue stays empty."""

    @pytest.mark.asyncio
    async def test_start_date_in_future_drops_article_and_flips_flag(self):
        s = _scraper_class("idnfinancials")(
            keywords="makan bergizi gratis",
            start_date=datetime(2099, 1, 1),
            queue_=asyncio.Queue(),
        )
        link = "https://www.idnfinancials.com/id/news/123/test-article"
        _attach_fetch(s, {link: _idn_article_html()})
        await s.get_article(link, "makan bergizi gratis")
        assert s.queue_.qsize() == 0
        assert s.continue_scraping is False


# ── Warta Ekonomi — discovery ───────────────────────────────────────────────


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
        return _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )

    @pytest.mark.asyncio
    async def test_build_search_url_page_one_posts_to_search(self):
        s = self._scraper()
        stub = _attach_fetch(
            s,
            {"/search": _warta_search_html(
                article_hrefs=[
                    {"href": "/read11111/makan-bergizi-gratis-headline",
                     "title": "Makan Bergizi Gratis Headline"},
                ],
                search_id="99",
            )},
        )
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
        stub = _attach_fetch(
            s,
            {
                "/search": _warta_search_html(
                    article_hrefs=[
                        {"href": "/read11111/makan-bergizi-gratis-headline",
                         "title": "Makan Bergizi Gratis Headline"},
                    ],
                    search_id="321",
                ),
                "/search/321": "<html></html>",
            },
        )
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
        s.parse_article_links(_warta_search_html(
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
        links = s.parse_article_links(_warta_search_html(
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
        links = s.parse_article_links(_warta_search_html(
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
        links = s.parse_article_links(_warta_search_html(
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
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/indeks": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0][0] == "https://wartaekonomi.co.id/indeks"

    @pytest.mark.asyncio
    async def test_page_two_appends_page_param(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"/indeks": "<html></html>"})
        await s.build_latest_url(2)
        assert stub.calls[0][0] == "https://wartaekonomi.co.id/indeks?page=2"

    @pytest.mark.asyncio
    async def test_indeks_url_embeds_start_date_token(self):
        """With start_date set, page 1 must hit ``/indeks/YYYYMMDD`` —
        the lower-date cutoff is encoded into the URL itself."""
        s = _scraper_class("wartaekonomi")(
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
        s = _scraper_class("wartaekonomi")(
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
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        links = s.parse_latest_article_links(_warta_indeks_html())
        assert links == {
            "https://wartaekonomi.co.id/read33333/indeks-article-one",
            "https://wartaekonomi.co.id/read44444/indeks-article-two",
        }

    def test_latest_parser_rejects_empty_body(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None


# ── Warta Ekonomi — extraction ──────────────────────────────────────────────


class TestWartaEkonomiGetArticle:
    """Warta Ekonomi article extraction contract: h1 (article h1 / .articlePostHeader h1)
    with og:title fallback, JSON-LD datePublished with meta/time fallbacks,
    JSON-LD author with meta fallback, JSON-LD articleSection with breadcrumb /
    meta fallbacks, body via .articlePostContent with noise-class stripping."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline"
        canonical = "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline"
        _attach_fetch(s, {link: _warta_article_html(canonical=canonical)})
        await s.get_article(link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
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
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
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
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read30000/empty"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "makan bergizi gratis")
        assert s.queue_.qsize() == 0

    @pytest.mark.asyncio
    async def test_missing_title_short_circuits(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
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



# ── Warta Ekonomi — metadata-free category path ─────────────────────────────


class TestWartaEkonomiMetadataFreeCategory:
    """Canonical ``/read{digits}/{slug}`` URLs with no JSON-LD ``articleSection``,
    no breadcrumb leaf under ``.articlePostHeader``, and no
    ``meta[property=article:section]``/``meta[name=category]`` must emit
    ``"Unknown"`` as the queued category. The article slug appears in the URL
    path but is never a category segment; emitting it is the regression this
    contract pins."""

    @pytest.mark.asyncio
    async def test_slug_not_emitted_as_category_when_no_metadata(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read12345/metadata-free-headline-slug"
        canonical = link
        # No JSON-LD articleSection, no .articlePostHeader ul li a breadcrumbs,
        # and no article:section / name=category meta. Title/date/content remain
        # intact so the article still passes the gate.
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

# ── Warta Ekonomi — canonical link contract ─────────────────────────────────


class TestWartaEkonomiCanonicalLink:
    """Warta Ekonomi must resolve the canonical link for the queued item.

    The contract is:

    1. If ``<link rel="canonical">`` exists, its ``href`` wins.
    2. Otherwise, ``<meta property="og:url">``'s ``content`` wins.
    3. If neither exists, the input ``link`` is used as the fallback.
    """

    @pytest.mark.asyncio
    async def test_link_rel_canonical_takes_priority(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        input_link = "https://wartaekonomi.co.id/read11111/some-article?utm_source=x"
        canonical = "https://wartaekonomi.co.id/read11111/some-article"
        _attach_fetch(s, {input_link: _warta_article_html(canonical=canonical)})
        await s.get_article(input_link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["link"] == canonical

    @pytest.mark.asyncio
    async def test_og_url_used_when_canonical_missing(self):
        """Without ``<link rel=canonical>``, ``og:url`` must drive the link."""
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
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
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        input_link = "https://wartaekonomi.co.id/read33333/fallback-link"
        _attach_fetch(s, {input_link: _warta_article_html(include_canonical=False)})
        await s.get_article(input_link, "makan bergizi gratis")

        item = s.queue_.get_nowait()
        assert item["link"] == input_link


# ── Warta Ekonomi — queue schema ────────────────────────────────────────────


class TestWartaEkonomiQueueSchema:
    """Warta Ekonomi queue items must contain exactly the eight contract
    keys with the expected types; source must be the canonical domain."""

    @pytest.mark.asyncio
    async def test_get_article_emits_exact_queue_schema(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline"
        _attach_fetch(s, {link: _warta_article_html(canonical=link)})
        await s.get_article(link, "makan bergizi gratis")

        assert s.queue_.qsize() == 1
        item = s.queue_.get_nowait()
        assert tuple(sorted(item)) == tuple(sorted(_QUEUE_KEYS))
        assert isinstance(item["publish_date"], datetime)
        assert isinstance(item["title"], str) and item["title"]
        assert isinstance(item["author"], str) and item["author"]
        assert isinstance(item["content"], str) and item["content"]
        assert item["keyword"] == "makan bergizi gratis"
        assert isinstance(item["category"], str) and item["category"]
        assert isinstance(item["source"], str) and item["source"]
        assert item["link"] == link
        assert item["source"] == "wartaekonomi.co.id"


# ── Warta Ekonomi — cutoff ──────────────────────────────────────────────────


class TestWartaEkonomiCutoff:
    """start_date in the future must drop the article and flip
    continue_scraping — the queue stays empty."""

    @pytest.mark.asyncio
    async def test_start_date_in_future_drops_article_and_flips_flag(self):
        s = _scraper_class("wartaekonomi")(
            keywords="makan bergizi gratis",
            start_date=datetime(2099, 1, 1),
            queue_=asyncio.Queue(),
        )
        link = "https://wartaekonomi.co.id/read12345/warta-ekonomi-test-headline"
        _attach_fetch(s, {link: _warta_article_html(canonical=link)})
        await s.get_article(link, "makan bergizi gratis")
        assert s.queue_.qsize() == 0
        assert s.continue_scraping is False


# ── Cross-adapter parametrized contracts ───────────────────────────────────


@pytest.mark.parametrize("slug", _NEW_SLUGS)
def test_registry_entry_status_and_capabilities(slug):
    """Every new adapter must be ``stable`` and support both search and latest."""
    entry = SCRAPERS[slug]
    assert entry.status == "stable", slug
    assert entry.supports_search is True, slug
    assert entry.supports_latest is True, slug
    assert entry.strict_search is True, slug
    assert entry.smoke_keyword, slug


@pytest.mark.parametrize("slug", _NEW_SLUGS)
def test_registry_entry_references_importable_class(slug):
    """The registry's module + class_name must resolve to an importable class
    that subclasses BaseScraper."""
    from newswatch.scrapers.basescraper import BaseScraper

    entry = SCRAPERS[slug]
    module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
    cls = getattr(module, entry.class_name)
    assert cls.__name__ == entry.class_name
    assert issubclass(cls, BaseScraper)