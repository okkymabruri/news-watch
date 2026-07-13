"""Deterministic offline tests for the seven finalized new adapters.

Finalized slugs (per project assignment):
    alinea, gnfi, betahita, nusabali, conversationid
                                         -> search + latest
    independen, hukumonline              -> latest only

The seven are derived from the registry source at module load via the
``Capability expansion: 2026-07`` section marker; this test never
hard-codes the slug list, so any new adapter added under that marker is
covered automatically.

Tests pin:
- registry-derived classification for each batch slug;
- discovery contracts per adapter (URL filters for search and latest,
  pagination, exact URL quoting, same-site canonical filtering, empty
  payload handling, /sorot/ support for Betahita);
- extraction contracts (one fixture test per distinct extraction family)
  covering all seven;
- start_date cutoff behavior across all seven;
- exact queue schema (title, publish_date, author, content, keyword,
  category, source, link) across all seven.

fetch() is stubbed in-process; no HTTP is performed.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from newswatch.registry import SCRAPERS


# ── Registry-derived batch discovery ────────────────────────────────────────


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_PATH = _PROJECT_ROOT / "src" / "newswatch" / "registry.py"
_BATCH_SECTION_RE = re.compile(
    r"# ── Capability expansion: 2026-07 ──+\s*\n(.*?)(?=\n    # ── |\Z)",
    re.DOTALL,
)
_SLUG_IN_ENTRY_RE = re.compile(r'ScraperEntry\(\s*\n?\s*"([a-z]+)"')


def _discover_batch_slugs() -> list[str]:
    """Read registry.py and return every slug declared in the
    ``Capability expansion: 2026-07`` section."""
    text = _REGISTRY_PATH.read_text(encoding="utf-8")
    match = _BATCH_SECTION_RE.search(text)
    if not match:
        return []
    return _SLUG_IN_ENTRY_RE.findall(match.group(1))


BATCH_SLUGS: list[str] = _discover_batch_slugs()

# Static partition derived from registry capability flags.
SEARCH_BATCH_SLUGS: list[str] = sorted(
    s for s in BATCH_SLUGS if SCRAPERS[s].supports_search
)
LATEST_BATCH_SLUGS: list[str] = sorted(
    s for s in BATCH_SLUGS if SCRAPERS[s].supports_latest
)
LATEST_ONLY_BATCH_SLUGS: list[str] = sorted(
    s for s in BATCH_SLUGS
    if SCRAPERS[s].supports_latest and not SCRAPERS[s].supports_search
)


def _scraper_class(slug: str) -> type:
    entry = SCRAPERS[slug]
    module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
    return getattr(module, entry.class_name)


# ── Fetch stub ──────────────────────────────────────────────────────────────


class _FetchStub:
    """Replace ``scraper.fetch`` with a URL-substring → body lookup.

    Returns the matched body for any URL containing one of the registered
    substrings; returns ``None`` otherwise so callers that key on falsy
    responses (e.g. Hukumonline's "no XML" guard) observe the same
    fall-through they would in production.
    """

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses: dict[str, str] = responses or {}
        self.calls: list[str] = []

    async def __call__(self, url: str, *args: Any, **kwargs: Any) -> str | None:
        self.calls.append(url)
        for needle, body in self.responses.items():
            if needle in url:
                return body
        return None


def _attach_fetch(scraper: Any, responses: dict[str, str]) -> _FetchStub:
    stub = _FetchStub(responses)
    scraper.fetch = stub
    return stub


# ── Article HTML / XML fixtures ─────────────────────────────────────────────


def _alinea_article_html(*, date_text: str = "12 Juli 2026") -> str:
    return f"""<!doctype html>
<html><head>
<meta property="og:title" content="Alinea test headline">
</head><body>
<h1>Alinea test headline</h1>
<div class="frontdate">{date_text}</div>
<div class="written__reporter">
  <div class="reporter__nama">Reporter Satu</div>
</div>
<article>
  <div>
    <p>Lead paragraph that is well over the forty character filter threshold for alinea's content extraction.</p>
    <p>Second body paragraph continuing the alinea story with enough length to remain in the extracted content blob.</p>
  </div>
</article>
</body></html>
"""


def _gnfi_article_html(*, jsonld_date: str = "2026-07-12T10:00:00+00:00") -> str:
    ld_payload = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "datePublished": jsonld_date,
        "author": {"@type": "Person", "name": "JSON-LD Reporter"},
    })
    return (
        '<!doctype html>\n<html><head>\n'
        '<meta property="og:title" content="GNFI test headline">\n'
        '<meta name="author" content="GNFI Reporter">\n'
        '<script type="application/ld+json">\n'
        f'{ld_payload}\n'
        '</script>\n'
        '</head><body>\n'
        '<div class="article-category"><a href="/c/lingkungan">Lingkungan</a></div>\n'
        '<div class="article-sheet">\n'
        '  <p data-path-to-node="0">GNFI lead paragraph that the article-sheet extractor pulls into the body.</p>\n'
        '  <p data-path-to-node="1">GNFI second paragraph continuing the article body extraction from the sheet node.</p>\n'
        '</div>\n'
        '</body></html>\n'
    )


def _conversation_article_html() -> str:
    return """<!doctype html>
<html><head>
<meta property="og:title" content="Conversation ID test headline">
</head><body>
<time datetime="2026-07-12T10:00:00Z">12 July 2026</time>
<a rel="author" href="/profile/author-one">Author One</a>
<a rel="author" href="/profile/author-two">Author Two</a>
<a href="/topics/politics">Politics</a>
<a href="/topics/economics">Economics</a>
<div itemprop="articleBody">
  <p>Conversation ID lead paragraph that the articleBody extractor pulls into the body text blob.</p>
  <p>Conversation ID second paragraph continuing the article body extraction below the byline.</p>
</div>
</body></html>
"""


def _betahita_article_html() -> str:
    return """<!doctype html>
<html><head>
</head><body>
<article class="detail-artikel">
  <div class="judul-artikel">
    <h5>Berita</h5>
    <h1>Betahita test headline</h1>
    <h5 class="margin-bottom-sm">Sabtu, 11 Juli 2026</h5>
  </div>
  <div class="box-sumber">
    <h5 class="title">Oleh: Betahita Reporter</h5>
  </div>
  <div class="detail-in">
    <p>Intro paragraph that should be skipped because the BETAHITA.ID dateline has not yet been seen.</p>
    <p>BETAHITA.ID — Betahita lead paragraph included by the post-dateline content extractor.</p>
    <p>Betahita second paragraph also included because it follows the dateline marker.</p>
    <div class="box-foto-artikel"><p>photo caption — must be retained as text</p></div>
  </div>
</article>
</body></html>
"""


def _nusabali_article_html() -> str:
    return """<!doctype html>
<html><head>
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
  <p>NusaBali lead paragraph pulled into the body by the entry-content extractor.</p>
  <p>NusaBali second paragraph also retained because it sits inside articleBody.</p>
</div>
</body></html>
"""


def _hukumonline_article_html() -> str:
    ld_payload = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "datePublished": "2026-07-12T10:00:00+07:00",
        "articleSection": "Hukum",
        "author": {"@type": "Person", "name": "Hukumonline Reporter"},
    })
    return (
        '<!doctype html>\n<html><head>\n'
        '<meta property="og:title" content="Hukumonline test headline">\n'
        '<script type="application/ld+json">\n'
        f'{ld_payload}\n'
        '</script>\n'
        '</head><body>\n'
        '<article>\n'
        '  <p>Hukumonline lead paragraph included by the article-descendant extractor.</p>\n'
        '  <p>Hukumonline second paragraph continuing the joined article body.</p>\n'
        '</article>\n'
        '</body></html>\n'
    )


def _hukumonline_sitemap_xml(urls: list[str]) -> str:
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        body += f"  <url><loc>{u}</loc></url>\n"
    body += "</urlset>\n"
    return body


def _independen_article_html() -> str:
    """Representative Drupal page for https://independen.id/{slug}."""
    return """<!doctype html>
<html><head>
<meta property="og:title" content="Independen test headline - Independen.id">
<meta property="article:published_time" content="2026-07-12T10:00:00+07:00">
<meta property="article:section" content="Investigasi">
<meta name="author" content="Independen Reporter">
</head><body>
<article>
  <p class="lead">Independen lead paragraph that survives the >=25 char filter inside the article extractor.</p>
  <p>Independen second paragraph continuing the joined article body from the static Drupal markup.</p>
  <div class="share-buttons"><a href="#">share</a></div>
  <div class="related-articles"><p>related noise — must be removed</p></div>
</article>
</body></html>
"""


# ── Queue schema (the contract) ─────────────────────────────────────────────


_QUEUE_KEYS: tuple[str, ...] = (
    "title", "publish_date", "author", "content",
    "keyword", "category", "source", "link",
)


# ── 1. Registry-derived classification ──────────────────────────────────────


class TestBatchDiscovery:
    """The seven finalized slugs must be discoverable from registry.py."""

    def test_batch_section_present(self):
        assert BATCH_SLUGS, "registry.py is missing the 2026-07 capability-expansion section"

    def test_batch_contains_seven_slugs(self):
        # Order-independent: count and contents must match the assignment contract.
        assert len(BATCH_SLUGS) == 7, f"expected 7 slugs, got {BATCH_SLUGS}"
        assert set(BATCH_SLUGS) == {
            "alinea", "gnfi", "betahita", "nusabali",
            "independen", "conversationid", "hukumonline",
        }

    def test_search_capable_partition(self):
        assert SEARCH_BATCH_SLUGS == [
            "alinea", "betahita", "conversationid", "gnfi", "nusabali",
        ]

    def test_latest_only_partition(self):
        assert LATEST_ONLY_BATCH_SLUGS == ["hukumonline", "independen"]

    @pytest.mark.parametrize("slug", BATCH_SLUGS)
    def test_batch_slug_is_stable(self, slug):
        assert SCRAPERS[slug].status == "stable", slug

    @pytest.mark.parametrize("slug", BATCH_SLUGS)
    def test_batch_slug_supports_latest(self, slug):
        assert SCRAPERS[slug].supports_latest is True, slug

    @pytest.mark.parametrize("slug", BATCH_SLUGS)
    def test_batch_slug_has_importable_class(self, slug):
        entry = SCRAPERS[slug]
        module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
        cls = getattr(module, entry.class_name)
        assert cls.__name__ == entry.class_name


# ── 2. Discovery: search-mode URL filters (existing) ───────────────────────


class TestAlineaSearchURLFiltering:
    """Alinea search: /search?q={keyword}&page=N — only the 5 sections count."""

    def _scraper(self):
        return _scraper_class("alinea")(
            keywords="politik",
            queue_=asyncio.Queue(),
        )

    @pytest.mark.asyncio
    async def test_page_one_uses_page_one(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"q=politik": "<html></html>"})
        body = await s.build_search_url("politik", 1)
        assert body == "<html></html>"
        assert len(stub.calls) == 1
        assert "q=politik" in stub.calls[0]
        assert "page=1" in stub.calls[0]

    @pytest.mark.asyncio
    async def test_page_two_adds_page_param(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"q=politik": "<html></html>"})
        await s.build_search_url("politik", 2)
        assert "page=2" in stub.calls[0]

    @pytest.mark.asyncio
    async def test_unicode_keyword_is_url_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"q=": "<html></html>"})
        await s.build_search_url("ekonomi & bisnis", 1)
        assert "ekonomi+%26+bisnis" in stub.calls[0] or "ekonomi%20%26%20bisnis" in stub.calls[0]

    def test_parser_keeps_section_articles_and_drops_offsite(self):
        s = self._scraper()
        html = """
        <html><body>
          <a href="/politik/foo-bar-b123">in-section</a>
          <a href="/gaya-hidup/baz-qux-b456">in-section-gaya-hidup</a>
          <a href="/search?q=foo">search page itself — must be dropped</a>
          <a href="/lain/foo">unknown section — must be dropped</a>
          <a href="https://example.com/politik/baz">off-site — must be dropped</a>
          <a>no href at all</a>
        </body></html>
        """
        links = s.parse_article_links(html)
        assert links == {
            "https://www.alinea.id/politik/foo-bar-b123",
            "https://www.alinea.id/gaya-hidup/baz-qux-b456",
        }
        # Empty case flips continue_scraping to stop the loop.
        assert s.parse_article_links("<html><body>no anchors here</body></html>") is None
        assert s.continue_scraping is False


class TestGNFISearchURLFiltering:
    """GNFI search: /search?keyword={quoted}[&page=N] — same-site dated URLs only."""

    def _scraper(self):
        return _scraper_class("gnfi")(
            keywords="bali",
            queue_=asyncio.Queue(),
        )

    @pytest.mark.asyncio
    async def test_page_one_uses_keyword_param_quoted(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("ekonomi & bisnis", 1)
        url = stub.calls[0]
        assert url.startswith("https://www.goodnewsfromindonesia.id/search?")
        # The ampersand and spaces must be percent-encoded.
        assert "keyword=ekonomi" in url
        assert "%26" in url
        assert "%20" in url
        # No raw "&" splitting the keyword from another query param.
        assert re.search(r"keyword=ekonomi[^%][^&]*&", url) is None
        # Page 1 omits page=
        assert "page=" not in url

    @pytest.mark.asyncio
    async def test_page_two_appends_page_param(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("bali", 2)
        assert stub.calls[0].endswith("&page=2")

    @pytest.mark.asyncio
    async def test_keyword_with_special_chars_round_trips(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("ekonomi & bisnis/ihsg+market", 1)
        # quote(safe="") percent-encodes everything except unreserved chars.
        expected = quote("ekonomi & bisnis/ihsg+market", safe="")
        assert expected in stub.calls[0]

    def test_parser_keeps_only_dated_same_site_urls(self):
        s = self._scraper()
        html = """
        <html><body>
          <a href="/2026/07/12/some-article">dated — kept</a>
          <a href="https://www.goodnewsfromindonesia.id/2025/12/01/old-article">dated absolute — kept</a>
          <a href="/c/lingkungan">category — dropped (no date path)</a>
          <a href="/about">about — dropped</a>
          <a href="https://other.example.com/2026/07/12/foreign">off-site — dropped</a>
          <a href="/2026/7/12/no-leading-zero">two-digit month, no zero pad — dropped</a>
        </body></html>
        """
        links = s.parse_article_links(html)
        assert links == {
            "https://www.goodnewsfromindonesia.id/2026/07/12/some-article",
            "https://www.goodnewsfromindonesia.id/2025/12/01/old-article",
        }


# ── 2b. Discovery: search-mode URL filters (newly search-capable) ──────────


class TestBetahitaSearchURLFiltering:
    """Betahita search: every page hits /search?query={quoted}&pagenum={page}
    (canonical server-rendered endpoint, no /berita|opini|sorot/{keyword}
    landing-page fallback walk). The same parser drives both latest and
    search mode and accepts canonical /{berita|opini|sorot}/{numeric-id}/{slug}
    articles from betahita.id, including /sorot/."""

    def _scraper(self):
        return _scraper_class("betahita")(
            keywords="lingkungan",
            queue_=asyncio.Queue(),
        )

    @pytest.mark.asyncio
    async def test_page_one_targets_canonical_search_endpoint(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        body = await s.build_search_url("lingkungan", 1)
        assert body == "<html></html>"
        assert len(stub.calls) == 1
        url = stub.calls[0]
        assert url.startswith("https://www.betahita.id/search?")
        assert "query=lingkungan" in url
        assert "pagenum=1" in url

    @pytest.mark.asyncio
    async def test_page_two_also_targets_canonical_search_endpoint(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("lingkungan", 2)
        assert len(stub.calls) == 1
        url = stub.calls[0]
        # Pagination stays on /search?query=&pagenum= for every page; no
        # /berita|opini|sorot/{keyword} landing-page fallback walk.
        assert url.startswith("https://www.betahita.id/search?")
        assert "query=lingkungan" in url
        assert "pagenum=2" in url
        assert "/berita/" not in url
        assert "/opini/" not in url
        assert "/sorot/" not in url

    @pytest.mark.asyncio
    async def test_keyword_is_percent_encoded_for_all_variants(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"/search?": "<html>ok</html>"})
        await s.build_search_url("ekonomi & bisnis", 1)
        expected = quote("ekonomi & bisnis", safe="")
        assert expected in stub.calls[0]

    def test_parser_keeps_berita_opini_and_sorot_canonical_articles(self):
        s = self._scraper()
        html = """
        <html><body>
          <a href="/berita/12345/some-slug">berita — kept</a>
          <a href="/opini/99/opinion-slug">opini — kept</a>
          <a href="/sorot/100/featured-slug">sorot — kept (canonical /sorot/{id}/{slug})</a>
          <a href="/berita/no-id/slug">no numeric id — dropped</a>
          <a href="/video/12345/some-slug">video — dropped</a>
          <a href="https://other.example.com/berita/1/foo">off-site — dropped</a>
          <a href="/sorot/keyword">/sorot/{keyword} landing page — dropped (no numeric id)</a>
          <a href="/berita/12345/">trailing slash, no slug — dropped</a>
        </body></html>
        """
        links = s.parse_article_links(html)
        assert links == {
            "https://www.betahita.id/berita/12345/some-slug",
            "https://www.betahita.id/opini/99/opinion-slug",
            "https://www.betahita.id/sorot/100/featured-slug",
        }

    def test_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None


class TestNusaBaliSearchURLFiltering:
    """NusaBali search: /search?keyword={quoted}&page={page};
    parser accepts /berita/{id}/{slug} only."""

    def _scraper(self):
        return _scraper_class("nusabali")(
            keywords="bali",
            queue_=asyncio.Queue(),
        )

    @pytest.mark.asyncio
    async def test_page_one_quotes_keyword_and_sets_page_one(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        body = await s.build_search_url("bali", 1)
        assert body == "<html></html>"
        url = stub.calls[0]
        assert url.startswith("https://www.nusabali.com/search?")
        assert "keyword=bali" in url
        assert "page=1" in url

    @pytest.mark.asyncio
    async def test_page_two_sets_page_two(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("bali", 2)
        assert "page=2" in stub.calls[0]
        assert stub.calls[0].startswith("https://www.nusabali.com/search?")

    @pytest.mark.asyncio
    async def test_unicode_keyword_is_percent_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("ekonomi & bisnis", 1)
        expected = quote("ekonomi & bisnis", safe="")
        assert expected in stub.calls[0]

    @pytest.mark.asyncio
    async def test_empty_fetch_returns_none(self):
        s = self._scraper()
        # No fetch stub attached — empty body bubbles up as None.
        assert await s.build_search_url("nobody-home", 1) is None

    def test_parser_keeps_only_berita_numeric_id_slug(self):
        s = self._scraper()
        html = """
        <html><body>
          <a href="/berita/225365/pria-mabuk-diamankan-polisi">article — kept</a>
          <a href="/berita/7/leading-zero">short numeric id — kept</a>
          <a href="/opini/123/foo">opini — dropped (parser only accepts /berita/)</a>
          <a href="/tag/bali">tag — dropped</a>
          <a href="/about">about — dropped</a>
          <a href="/berita/not-a-number/slug">non-numeric id — dropped</a>
        </body></html>
        """
        links = s.parse_article_links(html)
        assert links == {
            "https://www.nusabali.com/berita/225365/pria-mabuk-diamankan-polisi",
            "https://www.nusabali.com/berita/7/leading-zero",
        }

    def test_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None


class TestConversationIDSearchURLFiltering:
    """Conversation ID search: /id/search with the full query string;
    parser accepts /{slug}-{id} only — same filter as latest."""

    def _scraper(self):
        return _scraper_class("conversationid")(
            keywords="indonesia",
            queue_=asyncio.Queue(),
        )

    @pytest.mark.asyncio
    async def test_page_one_emits_canonical_search_query(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        body = await s.build_search_url("politik", 1)
        assert body == "<html></html>"
        url = stub.calls[0]
        assert url.startswith("https://theconversation.com/id/search?")
        # Exact query-string contract: every parameter in the prescribed order.
        assert "date=all" in url
        assert "date_from=" in url
        assert "date_to=" in url
        assert "language=id" in url
        assert "page=1" in url
        assert "q=politik" in url
        assert "sort=recency" in url

    @pytest.mark.asyncio
    async def test_page_two_swaps_page_param(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("politik", 2)
        assert "page=2" in stub.calls[0]

    @pytest.mark.asyncio
    async def test_unicode_keyword_is_percent_encoded(self):
        s = self._scraper()
        stub = _attach_fetch(s, {"": "<html></html>"})
        await s.build_search_url("ekonomi & bisnis", 1)
        expected = quote("ekonomi & bisnis", safe="")
        assert f"q={expected}" in stub.calls[0]

    @pytest.mark.asyncio
    async def test_empty_fetch_returns_none(self):
        s = self._scraper()
        assert await s.build_search_url("nobody-home", 1) is None

    def test_parser_keeps_articles_drops_section_paths(self):
        s = self._scraper()
        html = """
        <html><body>
          <a href="/some-article-12345">article — kept</a>
          <a href="https://theconversation.com/another-article-67890">absolute article — kept</a>
          <a href="/topics/climate-change">topics — dropped</a>
          <a href="/authors/jane-doe">authors — dropped</a>
          <a href="/partners/foo">partners — dropped</a>
          <a href="/id/about-us">section about — dropped</a>
          <a href="/newsletters/signup">newsletter — dropped</a>
        </body></html>
        """
        links = s.parse_article_links(html)
        assert links == {
            "https://theconversation.com/some-article-12345",
            "https://theconversation.com/another-article-67890",
        }

    def test_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_article_links("") is None


# ── 3. Discovery: latest-mode URL filters (existing) ───────────────────────


class TestAlineaLatestURLFiltering:
    """Alinea latest: page 1 only, /indeks; reuse of search parser."""

    @pytest.mark.asyncio
    async def test_page_one_targets_indeks(self):
        s = _scraper_class("alinea")(
            keywords="politik", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"indeks": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0].endswith("/indeks")

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = _scraper_class("alinea")(
            keywords="politik", queue_=asyncio.Queue(),
        )
        # No fetch attached — if the adapter tries to call it, the test fails.
        assert await s.build_latest_url(2) is None


class TestGNFILatestURLFiltering:
    """GNFI latest: page 1 only, /explore."""

    @pytest.mark.asyncio
    async def test_page_one_targets_explore(self):
        s = _scraper_class("gnfi")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"explore": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0].endswith("/explore")

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = _scraper_class("gnfi")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(2) is None


class TestBetahitaLatestURLFiltering:
    """Betahita latest: page 1 only, /."""

    @pytest.mark.asyncio
    async def test_page_one_targets_homepage(self):
        s = _scraper_class("betahita")(
            keywords="lingkungan", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"betahita.id": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0] == "https://www.betahita.id"

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = _scraper_class("betahita")(
            keywords="lingkungan", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(2) is None


class TestNusaBaliLatestURLFiltering:
    """NusaBali latest: page 1 only, /."""

    @pytest.mark.asyncio
    async def test_page_one_targets_homepage(self):
        s = _scraper_class("nusabali")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"nusabali.com": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0] == "https://www.nusabali.com"

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = _scraper_class("nusabali")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(2) is None


class TestConversationIDLatestURLFiltering:
    """Conversation ID latest: page 1 only, /id."""

    @pytest.mark.asyncio
    async def test_page_one_targets_id_homepage(self):
        s = _scraper_class("conversationid")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"theconversation.com/id": "<html></html>"})
        body = await s.build_latest_url(1)
        assert body == "<html></html>"
        assert stub.calls[0] == "https://theconversation.com/id"

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = _scraper_class("conversationid")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(2) is None


# ── 3b. Latest-only homepage filters (existing) ────────────────────────────


class TestConversationIDHomepageFiltering:
    """Conversation ID keeps /{slug}-{id}, drops topics / partners / authors."""

    def test_parser_keeps_articles_drops_section_paths(self):
        s = _scraper_class("conversationid")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        html = """
        <html><body>
          <a href="/some-article-12345">article — kept</a>
          <a href="https://theconversation.com/another-article-67890">absolute article — kept</a>
          <a href="/topics/climate-change">topics — dropped</a>
          <a href="/authors/jane-doe">authors — dropped</a>
          <a href="/partners/foo">partners — dropped</a>
          <a href="/id/about-us">section about — dropped</a>
          <a href="/newsletters/signup">newsletter — dropped</a>
        </body></html>
        """
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://theconversation.com/some-article-12345",
            "https://theconversation.com/another-article-67890",
        }

    def test_parser_rejects_empty_body(self):
        s = _scraper_class("conversationid")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None


class TestBetahitaHomepageFiltering:
    """Betahita keeps /{berita|opini}/{numeric-id}/{slug} only."""

    def test_parser_keeps_berita_and_opini_drops_other_paths(self):
        s = _scraper_class("betahita")(
            keywords="lingkungan", queue_=asyncio.Queue(),
        )
        html = """
        <html><body>
          <a href="/berita/12345/some-slug">berita — kept</a>
          <a href="/opini/99/opinion-slug">opini — kept</a>
          <a href="/video/12345/some-slug">video — dropped</a>
          <a href="/tentang-kami">about — dropped</a>
          <a href="/berita/no-id/slug">no numeric id — dropped</a>
          <a href="https://www.betahita.id/berita/7/leading-zero-id">leading-zero id — kept</a>
        </body></html>
        """
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://www.betahita.id/berita/12345/some-slug",
            "https://www.betahita.id/opini/99/opinion-slug",
            "https://www.betahita.id/berita/7/leading-zero-id",
        }

    def test_parser_rejects_empty_body(self):
        s = _scraper_class("betahita")(
            keywords="lingkungan", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None


class TestNusaBaliHomepageFiltering:
    """NusaBali keeps /berita/{numeric-id}/{slug} only."""

    def test_parser_keeps_only_berita_numeric_id_slug(self):
        s = _scraper_class("nusabali")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        html = """
        <html><body>
          <a href="/berita/225365/pria-mabuk-diamankan-polisi">article — kept</a>
          <a href="/berita/7/leading-zero">short numeric id — kept</a>
          <a href="/opini/123/foo">opini — dropped (no /opini/ support)</a>
          <a href="/tag/bali">tag — dropped</a>
          <a href="/about">about — dropped</a>
          <a href="/berita/not-a-number/slug">non-numeric id — dropped</a>
        </body></html>
        """
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://www.nusabali.com/berita/225365/pria-mabuk-diamankan-polisi",
            "https://www.nusabali.com/berita/7/leading-zero",
        }

    def test_parser_rejects_empty_body(self):
        s = _scraper_class("nusabali")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        assert s.parse_latest_article_links("") is None


# ── 4. Discovery: Hukumonline urlset + non-XML rejection ───────────────────


class TestHukumonlineUrlsetAndRejection:
    """Hukumonline parses /berita/sitemap.xml and rejects Cloudflare HTML."""

    @pytest.mark.asyncio
    async def test_build_latest_url_targets_sitemap(self):
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
        stub = _attach_fetch(s, {"": _hukumonline_sitemap_xml([])})
        await s.build_latest_url(1)
        assert stub.calls[0] == "https://www.hukumonline.com/berita/sitemap.xml"

    @pytest.mark.asyncio
    async def test_page_two_is_none(self):
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
        assert await s.build_latest_url(2) is None

    def test_parser_keeps_berita_a_slugs_drops_foto_and_stories(self):
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
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
        # Parser does not dedupe — trailing-slash variant survives as a
        # separate entry (the regex match still succeeds on the stripped
        # form). Multi-segment allowed. foto/stories excluded. Empty slug
        # and wrong prefix dropped.
        assert links == [
            "https://www.hukumonline.com/berita/a/canonical-slug",
            "https://www.hukumonline.com/berita/a/multi-segment/slug",
            "https://www.hukumonline.com/berita/a/canonical-slug-with-trailing",
        ]

    def test_parser_rejects_non_xml_html_response(self):
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
        cloudflare = (
            "<!doctype html><html><head><title>Just a moment...</title>"
            "</head><body>Please enable JavaScript to continue.</body></html>"
        )
        assert s.parse_latest_article_links(cloudflare) is None

    def test_parser_rejects_html_without_doctype_marker(self):
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
        # No <?xml and no <urlset in the head — must be rejected as non-XML.
        assert s.parse_latest_article_links(
            "<html><body>unexpected HTML body without sitemap markers</body></html>"
        ) is None

    def test_parser_rejects_malformed_xml(self):
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
        # Starts with <?xml but body is broken.
        assert s.parse_latest_article_links(
            "<?xml version='1.0'?><urlset><url><loc>oops</loc></url"
        ) is None


# ── 4b. Independen homepage discovery (replaces BenarNews) ────────────────


class TestIndependenHomepageFiltering:
    """Independen keeps root-level /{slug}(/{slug})* URLs only; rejects
    Drupal route prefixes (node/, taxonomy/, user/, tags/, agenda/, etc.)
    and asset extensions. Canonical form is slashless."""

    def _scraper(self):
        return _scraper_class("independen")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )

    def test_parser_keeps_root_level_slugs_only(self):
        s = self._scraper()
        html = """
        <html><body>
          <a href="/judul-artikel-contoh">article slug — kept</a>
          <a href="https://independen.id/artikel/lainnya">absolute root — kept</a>
          <a href="/node/12345">drupal canonical node — dropped</a>
          <a href="/taxonomy/term/7">taxonomy — dropped</a>
          <a href="/user/42">user — dropped</a>
          <a href="/users/42">users alias — dropped</a>
          <a href="/tags/bencana">tags landing — dropped</a>
          <a href="/tag/bencana">tag landing — dropped</a>
          <a href="/agenda/2026-07-12">agenda — dropped</a>
          <a href="/category/legacy">category alias — dropped</a>
          <a href="/kategori/legacy">kategori alias — dropped</a>
          <a href="/frontpages">front page — dropped</a>
          <a href="/front-page">front page variant — dropped</a>
          <a href="/about">about — dropped</a>
          <a href="/contact">contact — dropped</a>
          <a href="/kontak">kontak — dropped</a>
          <a href="/pedoman">pedoman — dropped</a>
          <a href="/ketentuan">ketentuan — dropped</a>
          <a href="/privacy">privacy — dropped</a>
          <a href="/advertise">advertise — dropped</a>
          <a href="/iklan">iklan — dropped</a>
          <a href="/redaksi">redaksi — dropped</a>
          <a href="/penulis">penulis — dropped</a>
          <a href="/kolom">kolom — dropped</a>
          <a href="/search">search — dropped</a>
          <a href="/berita">section landing — dropped</a>
          <a href="/politik">section landing — dropped</a>
          <a href="/hukum-dan-ham">section landing — dropped</a>
          <a href="/ekonomi">section landing — dropped</a>
          <a href="/lingkungan">section landing — dropped</a>
          <a href="/kesehatan">section landing — dropped</a>
          <a href="/teknologi">section landing — dropped</a>
          <a href="/pendidikan">section landing — dropped</a>
          <a href="/budaya">section landing — dropped</a>
          <a href="/opini">section landing — dropped</a>
          <a href="/feature">section landing — dropped</a>
          <a href="/investigasi">section landing — dropped</a>
          <a href="/infografis">section landing — dropped</a>
          <a href="/video">section landing — dropped</a>
          <a href="/foto">section landing — dropped</a>
          <a href="/galeri">section landing — dropped</a>
          <a href="/live">section landing — dropped</a>
          <a href="/">homepage self — dropped</a>
          <a href="/image.png">asset — dropped</a>
          <a href="/document.pdf">asset — dropped</a>
        </body></html>
        """
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://independen.id/judul-artikel-contoh",
            "https://independen.id/artikel/lainnya",
        }

    def test_parser_strips_query_and_fragment(self):
        s = self._scraper()
        html = """
        <html><body>
          <a href="/judul?ref=home">query — kept, canonical</a>
          <a href="/other-article#section">fragment — kept, canonical</a>
        </body></html>
        """
        links = s.parse_latest_article_links(html)
        assert links == {
            "https://independen.id/judul",
            "https://independen.id/other-article",
        }

    def test_parser_rejects_empty_body(self):
        s = self._scraper()
        assert s.parse_latest_article_links("") is None
        assert s.parse_latest_article_links(None) is None  # type: ignore[arg-type]


# ── 5. get_article fixture tests — one per extraction family ───────────────


class TestAlineaGetArticle:
    """Alinea: og:title, div.frontdate (Indonesian), reporter, path category."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("alinea")(
            keywords="politik", queue_=asyncio.Queue(),
        )
        link = "https://www.alinea.id/politik/foo-bar-b123"
        _attach_fetch(s, {link: _alinea_article_html()})
        await s.get_article(link, "politik")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
        assert item["title"] == "Alinea test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 0, 0, 0)
        assert item["author"] == "Reporter Satu"
        assert "alinea" in item["content"].lower() or len(item["content"]) > 50
        assert item["keyword"] == "politik"
        assert item["category"] == "politik"  # path segment
        assert item["source"] == "www.alinea.id"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_empty_body_short_circuits_without_put(self):
        s = _scraper_class("alinea")(
            keywords="politik", queue_=asyncio.Queue(),
        )
        link = "https://www.alinea.id/politik/empty"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "politik")
        assert s.queue_.qsize() == 0


class TestGNFIGetArticle:
    """GNFI: og:title, JSON-LD datePublished (naive UTC), article-sheet p."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("gnfi")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        link = "https://www.goodnewsfromindonesia.id/2026/07/12/test-article"
        _attach_fetch(s, {link: _gnfi_article_html()})
        await s.get_article(link, "bali")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
        assert item["title"] == "GNFI test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 10, 0, 0)
        assert item["publish_date"].tzinfo is None
        # Author comes from meta[name=author] first; JSON-LD is the fallback.
        assert item["author"] == "GNFI Reporter"
        assert item["category"] == "Lingkungan"
        assert item["source"] == "goodnewsfromindonesia.id"
        assert item["keyword"] == "bali"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_missing_date_short_circuits(self):
        s = _scraper_class("gnfi")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        link = "https://www.goodnewsfromindonesia.id/2026/07/12/no-date"
        html = """<!doctype html><html><head>
<meta property="og:title" content="t">
<meta name="author" content="a">
</head><body><div class="article-sheet">
<p data-path-to-node="0">body</p></div></body></html>"""
        _attach_fetch(s, {link: html})
        await s.get_article(link, "bali")
        assert s.queue_.qsize() == 0


class TestIndependenGetArticle:
    """Independen: og:title (with "- Independen.id" suffix stripped),
    article:published_time (naive UTC), meta[name=author], article:section."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("independen")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        link = "https://independen.id/judul-artikel-contoh/"
        _attach_fetch(s, {link: _independen_article_html()})
        await s.get_article(link, "indonesia")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
        # og:title suffix "- Independen.id" must be stripped.
        assert item["title"] == "Independen test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 3, 0, 0)
        assert item["publish_date"].tzinfo is None
        assert item["author"] == "Independen Reporter"
        assert item["category"] == "Investigasi"
        assert item["source"] == "independen.id"
        assert item["keyword"] == "indonesia"
        assert item["link"] == link
        # Content must come from the <article> node and skip the share/related
        # blocks. Short paragraphs (<25 chars) are filtered out; lead paragraph
        # survives because it is well over the threshold.
        assert "Independen lead paragraph" in item["content"]
        assert "share" not in item["content"].lower().split(" second ")[0]
        assert "related noise" not in item["content"]

    @pytest.mark.asyncio
    async def test_empty_body_short_circuits_without_put(self):
        s = _scraper_class("independen")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        link = "https://independen.id/empty/"
        _attach_fetch(s, {link: ""})
        await s.get_article(link, "indonesia")
        assert s.queue_.qsize() == 0

    @pytest.mark.asyncio
    async def test_missing_title_short_circuits(self):
        s = _scraper_class("independen")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        link = "https://independen.id/no-title/"
        html = """<!doctype html><html><head>
<meta property="article:published_time" content="2026-07-12T10:00:00+07:00">
</head><body><article><p>body paragraph over twenty-five chars long</p></article></body></html>"""
        _attach_fetch(s, {link: html})
        await s.get_article(link, "indonesia")
        assert s.queue_.qsize() == 0


class TestConversationIDGetArticle:
    """Conversation ID: og:title, time[datetime] naive UTC, multi-author."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("conversationid")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        link = "https://theconversation.com/some-article-12345"
        _attach_fetch(s, {link: _conversation_article_html()})
        await s.get_article(link, "indonesia")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
        assert item["title"] == "Conversation ID test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 10, 0, 0)
        assert item["publish_date"].tzinfo is None
        # Multi-author joined with comma, preserving insertion order.
        assert item["author"] == "Author One, Author Two"
        assert item["category"] == "Politics, Economics"
        assert item["source"] == "theconversation.com"
        assert item["keyword"] == "indonesia"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_missing_time_falls_back_to_meta(self):
        s = _scraper_class("conversationid")(
            keywords="indonesia", queue_=asyncio.Queue(),
        )
        link = "https://theconversation.com/fallback-article-99999"
        html = """<!doctype html><html><head>
<meta property="og:title" content="t">
<meta property="article:published_time" content="2026-07-12T12:00:00Z">
</head><body><div itemprop="articleBody">
<p>Conversation ID fallback body paragraph for the meta-only date path.</p></div></body></html>"""
        _attach_fetch(s, {link: html})
        await s.get_article(link, "indonesia")

        item = s.queue_.get_nowait()
        assert item["publish_date"] == datetime(2026, 7, 12, 12, 0, 0)
        assert item["publish_date"].tzinfo is None


class TestBetahitaGetArticle:
    """Betahita: h1 in judul-artikel, Indonesian locale date, Oleh prefix, dateline."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("betahita")(
            keywords="lingkungan", queue_=asyncio.Queue(),
        )
        link = "https://www.betahita.id/berita/12345/test-article"
        _attach_fetch(s, {link: _betahita_article_html()})
        await s.get_article(link, "lingkungan")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
        assert item["title"] == "Betahita test headline"
        assert item["publish_date"] == datetime(2026, 7, 11, 0, 0, 0)
        assert item["publish_date"].tzinfo is None
        assert item["author"] == "Betahita Reporter"
        assert item["category"] == "Berita"
        assert item["source"] == "betahita.id"
        assert item["link"] == link
        # Content skips pre-dateline paragraphs and includes the dateline row.
        assert "Intro paragraph" not in item["content"]
        assert "Betahita lead paragraph" in item["content"]
        assert "Betahita second paragraph" in item["content"]

    @pytest.mark.asyncio
    async def test_opini_url_derives_category_opini(self):
        s = _scraper_class("betahita")(
            keywords="lingkungan", queue_=asyncio.Queue(),
        )
        link = "https://www.betahita.id/opini/99/opinion-piece"
        # Same body but an Opini header — title still extracted, category flips.
        html = _betahita_article_html().replace("<h5>Berita</h5>", "<h5>Opini</h5>")
        _attach_fetch(s, {link: html})
        await s.get_article(link, "lingkungan")

        item = s.queue_.get_nowait()
        assert item["category"] == "Opini"


class TestNusaBaliGetArticle:
    """NusaBali: og:title, span.month datePublished, span[itemprop=author],
    breadcrumb category."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("nusabali")(
            keywords="bali", queue_=asyncio.Queue(),
        )
        link = "https://www.nusabali.com/berita/225365/pria-mabuk-di-desa-keramas"
        _attach_fetch(s, {link: _nusabali_article_html()})
        await s.get_article(link, "bali")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
        assert item["title"] == "NusaBali test headline"
        assert item["publish_date"] == datetime(2026, 7, 12, 19, 37, 24)
        assert item["publish_date"].tzinfo is None
        # "Penulis : " prefix is kept verbatim in the author field.
        assert item["author"] == "Penulis : I Putu Reporter"
        assert item["category"] == "Denpasar"
        assert item["source"] == "nusabali.com"
        assert item["link"] == link

    @pytest.mark.asyncio
    async def test_category_falls_back_to_unknown_when_no_breadcrumb(self):
        s = _scraper_class("nusabali")(
            keywords="bali", queue_=asyncio.Queue(),
        )
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
        _attach_fetch(s, {link: html})
        await s.get_article(link, "bali")

        item = s.queue_.get_nowait()
        assert item["category"] == "Unknown"


class TestHukumonlineGetArticle:
    """Hukumonline: og:title, JSON-LD datePublished, NewsArticle author/section."""

    @pytest.mark.asyncio
    async def test_extracts_full_queue_item(self):
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
        link = "https://www.hukumonline.com/berita/a/canonical-slug"
        _attach_fetch(s, {link: _hukumonline_article_html()})
        await s.get_article(link, "hukum")

        item = s.queue_.get_nowait()
        assert set(item) == set(_QUEUE_KEYS)
        assert item["title"] == "Hukumonline test headline"
        # dateparser returns tz-aware for +07:00; we only assert the calendar value.
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
        s = _scraper_class("hukumonline")(
            keywords="hukum", queue_=asyncio.Queue(),
        )
        link = "https://www.hukumonline.com/berita/a/fallback-section"
        ld_payload = json.dumps({
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "datePublished": "2026-07-12T10:00:00+07:00",
            "author": {"@type": "Person", "name": "x"},
        })
        html = (
            '<!doctype html><html><head>\n'
            '<meta property="og:title" content="t">\n'
            '<meta property="article:section" content="Bisnis">\n'
            '<script type="application/ld+json">\n'
            f'{ld_payload}\n'
            '</script>\n'
            '</head><body>\n'
            '<article>\n'
            '  <p>Hukumonline fallback body paragraph for the meta-section test path.</p>\n'
            '</article>\n'
            '</body></html>\n'
        )
        _attach_fetch(s, {link: html})
        await s.get_article(link, "hukum")

        item = s.queue_.get_nowait()
        assert item["category"] == "Bisnis"


# ── 6. Cutoff behavior — start_date in the future must stop the run ─────────


CUTOFF_FUTURE = datetime(2099, 1, 1)


def _cutoff_article_html_for(slug: str, link: str) -> dict[str, str]:
    """Return the same article HTML used by the per-family extraction tests."""
    return {link: _article_html_for(slug)}


def _article_html_for(slug: str) -> str:
    if slug == "alinea":
        return _alinea_article_html()
    if slug == "gnfi":
        return _gnfi_article_html()
    if slug == "independen":
        return _independen_article_html()
    if slug == "conversationid":
        return _conversation_article_html()
    if slug == "betahita":
        return _betahita_article_html()
    if slug == "nusabali":
        return _nusabali_article_html()
    if slug == "hukumonline":
        return _hukumonline_article_html()
    raise AssertionError(f"no article fixture for slug {slug!r}")


def _sample_article_link_for(slug: str) -> str:
    """Return a representative same-site URL accepted by the scraper."""
    if slug == "alinea":
        return "https://www.alinea.id/politik/foo-bar-b123"
    if slug == "gnfi":
        return "https://www.goodnewsfromindonesia.id/2026/07/12/test-article"
    if slug == "independen":
        return "https://independen.id/judul-artikel-contoh/"
    if slug == "conversationid":
        return "https://theconversation.com/some-article-12345"
    if slug == "betahita":
        return "https://www.betahita.id/berita/12345/test-article"
    if slug == "nusabali":
        return "https://www.nusabali.com/berita/225365/pria-mabuk-di-desa-keramas"
    if slug == "hukumonline":
        return "https://www.hukumonline.com/berita/a/canonical-slug"
    raise AssertionError(f"no sample link for slug {slug!r}")


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", BATCH_SLUGS)
async def test_start_date_in_future_drops_article_and_flips_flag(slug):
    """Every batch scraper must refuse articles older than start_date and
    signal the loop to stop. The queue must stay empty."""
    link = _sample_article_link_for(slug)
    s = _scraper_class(slug)(
        keywords=SCRAPERS[slug].smoke_keyword,
        start_date=CUTOFF_FUTURE, queue_=asyncio.Queue(),
    )
    _attach_fetch(s, _cutoff_article_html_for(slug, link))
    await s.get_article(link, SCRAPERS[slug].smoke_keyword)

    assert s.queue_.qsize() == 0, f"{slug} queued an article older than start_date"
    assert s.continue_scraping is False, f"{slug} did not flip continue_scraping"


# ── 7. Queue schema contract — exactly the eight contract keys ──────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", BATCH_SLUGS)
async def test_get_article_emits_exact_queue_schema(slug):
    """Every batch scraper must put exactly the eight contract keys; nothing
    else; publish_date must be a datetime instance."""
    link = _sample_article_link_for(slug)
    s = _scraper_class(slug)(
        keywords=SCRAPERS[slug].smoke_keyword,
        queue_=asyncio.Queue(),
    )
    _attach_fetch(s, _cutoff_article_html_for(slug, link))
    await s.get_article(link, SCRAPERS[slug].smoke_keyword)
    assert s.queue_.qsize() == 1, f"{slug} put no item"
    item = s.queue_.get_nowait()
    assert tuple(sorted(item)) == tuple(sorted(_QUEUE_KEYS)), (
        f"{slug} queue item has unexpected keys: "
        f"extra={set(item) - set(_QUEUE_KEYS)} missing={set(_QUEUE_KEYS) - set(item)}"
    )
    assert isinstance(item["publish_date"], datetime), slug
    assert isinstance(item["title"], str) and item["title"]
    assert isinstance(item["author"], str) and item["author"]
    assert isinstance(item["content"], str) and item["content"]
    assert item["keyword"] == SCRAPERS[slug].smoke_keyword
    assert isinstance(item["category"], str) and item["category"]
    assert isinstance(item["source"], str) and item["source"]
    assert item["link"] == link


# Calendar dates asserted by the cutoff/schema parametrized tests.
# Each scraper normalizes timezone handling differently (UTC, local-naive,
# raw-aware). We compare only the naive calendar value via {expected}, since
# the *contract* is that the queue schema field is a datetime — not the
# specific timezone normalization policy per scraper.
_ARTICLE_FIXTURE_DATES: dict[str, datetime] = {
    "alinea": datetime(2026, 7, 12, 0, 0, 0),
    "gnfi": datetime(2026, 7, 12, 10, 0, 0),
    "independen": datetime(2026, 7, 12, 3, 0, 0),
    "conversationid": datetime(2026, 7, 12, 10, 0, 0),
    "betahita": datetime(2026, 7, 11, 0, 0, 0),
    "nusabali": datetime(2026, 7, 12, 19, 37, 24),
    # Hukumonline parses via dateparser without tzinfo stripping; we only
    # assert the calendar value elsewhere, so the contract test compares the
    # raw aware-datetime's naive wall-clock representation.
    "hukumonline": datetime(2026, 7, 12, 10, 0, 0),
}