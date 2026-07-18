"""
IDX Channel (idxchannel.com) scraper — sitemap-driven.

Verified endpoints (2026-07-18):
    index:  https://www.idxchannel.com/sitemap.xml          (sitemapindex)
    sitemaps: per-category news sitemaps, e.g.
        https://www.idxchannel.com/news/sitemap.xml
        https://www.idxchannel.com/market-news/sitemap.xml
        https://www.idxchannel.com/economics/sitemap.xml
        https://www.idxchannel.com/technology/sitemap.xml
        (other category sitemaps discovered from the index)
    article: https://www.idxchannel.com/<category>/<slug>

The /search endpoint returns HTTP 522 from public scraper peers, so search
uses the bounded category-news sitemap set instead. Sitemap entries carry
<news:title> plus <loc>; search fetches the set once and applies every-token
matching to combined title + URL text. Latest mode maps each page to one
category sitemap without keyword filtering.
"""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

_SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_SITEMAP_NSMAP = {"sm": _SM_NS, "news": _NEWS_NS}

_BASE_URL = "https://www.idxchannel.com"
_SITEMAP_INDEX_URL = f"{_BASE_URL}/sitemap.xml"

# Required minimum set of news-category sitemaps (confirmed via the sitemap
# index). The scraper additionally pulls every other category sitemap it
# discovers from the index that is not on the explicit deny list.
_REQUIRED_NEWS_SITEMAPS = (
    f"{_BASE_URL}/news/sitemap.xml",
    f"{_BASE_URL}/market-news/sitemap.xml",
    f"{_BASE_URL}/economics/sitemap.xml",
    f"{_BASE_URL}/technology/sitemap.xml",
)

# Category slugs whose sitemaps do not carry <news:title> news entries or
# are non-article surfaces. Keep out of discovery even if the index lists
# them, so article matching stays on news content.
_NON_NEWS_SITEMAP_RE = re.compile(
    r"/(?:foto|video|infografis)/sitemap\.xml$",
    re.IGNORECASE,
)

# Canonical article URL: one-segment category + slug. Multipage suffixes are rejected.
_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?idxchannel\.com/[a-z][a-z0-9-]+/[a-z0-9][a-z0-9-]*/?$",
    re.IGNORECASE,
)
_OFF_DOMAIN_RE = re.compile(r"^https?://(?:www\.)?idxchannel\.com/", re.IGNORECASE)

_NOISE_CLASS_RE = re.compile(
    r"baca[_-]juga|berita[_-]terkait|berita[_-]rekomendasi|share|"
    r"social|sidebar|footer|nav|promo|ads|advert|comment|newsletter|"
    r"recommended|related",
    re.IGNORECASE,
)


def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _keyword_tokens(keyword):
    return [tok for tok in re.split(r"\W+", (keyword or "").lower()) if len(tok) > 1]


def _matches_all_tokens(haystack, tokens):
    if not tokens:
        return True
    if not haystack:
        return False
    return all(re.search(rf"\b{re.escape(tok)}\b", haystack) for tok in tokens)


def _to_naive(value):
    """Strip tz info for the queue payload; dateparser may return aware datetimes."""
    if value is None:
        return None
    if value.tzinfo is not None:
        try:
            return value.replace(tzinfo=None)
        except (AttributeError, ValueError):
            return value
    return value


def _is_canonical_article(url):
    """Accept only same-site one-segment-category/slug URLs without page suffixes."""
    if not url or not _OFF_DOMAIN_RE.match(url):
        return False
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host not in ("idxchannel.com", "www.idxchannel.com"):
        return False
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2:
        return False
    return bool(_ARTICLE_RE.match(url))


class IDXChannelScraper(BaseScraper):
    """IDX Channel scraper driven by XML news sitemaps."""

    BASE_URL = _BASE_URL
    SITEMAP_INDEX_URL = _SITEMAP_INDEX_URL
    SOURCE_LABEL = "idxchannel.com"
    MAX_ARTICLES_PER_QUERY = 5

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = self.BASE_URL
        self.start_date = start_date
        self.max_latest_pages = len(_REQUIRED_NEWS_SITEMAPS) + 6
        self._news_sitemaps = None
        self._current_keyword = ""
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    # ------------------------------------------------------------------
    # Sitemap discovery
    # ------------------------------------------------------------------
    async def _discover_news_sitemaps(self):
        """Return the ordered list of news-category sitemap URLs.

        Order is: required entries first (in declaration order), then any
        additional same-site category sitemaps discovered from the sitemap
        index that are not on the non-news deny list.
        """
        discovered = []
        if self._news_sitemaps is not None:
            return self._news_sitemaps

        seen = set()

        for required in _REQUIRED_NEWS_SITEMAPS:
            if required not in seen:
                discovered.append(required)
                seen.add(required)

        index_text = await self.fetch(
            self.SITEMAP_INDEX_URL, headers=self.headers, timeout=30
        )
        if not index_text:
            self._news_sitemaps = discovered
            return self._news_sitemaps

        try:
            root = ET.fromstring(index_text)
        except ET.ParseError as e:
            logging.error("IDXChannel sitemap index parse error: %s", e)
            self._news_sitemaps = discovered
            return self._news_sitemaps

        for sitemap in root.findall("sm:sitemap", _SITEMAP_NSMAP):
            loc_el = sitemap.find("sm:loc", _SITEMAP_NSMAP)
            loc = (loc_el.text or "").strip() if loc_el is not None else ""
            if not loc or loc in seen:
                continue
            if not _OFF_DOMAIN_RE.match(loc):
                continue
            if _NON_NEWS_SITEMAP_RE.search(loc):
                continue
            discovered.append(loc)
            seen.add(loc)

        self._news_sitemaps = discovered[: self.max_latest_pages]
        return self._news_sitemaps

    @staticmethod
    def _parse_sitemap_xml(response_text):
        """Return list of (loc, news_title) tuples from a sitemap urlset."""
        if not response_text:
            return []
        head = response_text.lstrip()[:64].lower()
        if not head.startswith("<?xml") and "<urlset" not in head:
            return []
        try:
            root = ET.fromstring(response_text)
        except ET.ParseError as e:
            logging.error("IDXChannel sitemap parse error: %s", e)
            return []
        if root.tag != f"{{{_SM_NS}}}urlset":
            return []

        entries = []
        for url in root.findall("sm:url", _SITEMAP_NSMAP):
            loc_el = url.find("sm:loc", _SITEMAP_NSMAP)
            loc = (loc_el.text or "").strip() if loc_el is not None else ""
            if not loc:
                continue
            if not _is_canonical_article(loc):
                continue
            title = ""
            news_el = url.find("news:news", _SITEMAP_NSMAP)
            if news_el is not None:
                title_el = news_el.find("news:title", _SITEMAP_NSMAP)
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()
            entries.append((loc, title))
        return entries

    async def _fetch_sitemap_entries(self, sitemap_url):
        text = await self.fetch(sitemap_url, headers=self.headers, timeout=30)
        if not text:
            return []
        return self._parse_sitemap_xml(text)

    def _sitemap_for_page(self, page, sitemap_list):
        """Page index → one sitemap. Stops when the list is exhausted."""
        if page < 1 or page > len(sitemap_list):
            return None
        return sitemap_list[page - 1]

    # ------------------------------------------------------------------
    # Search path: keyword-filtered sitemap entries
    # ------------------------------------------------------------------
    async def build_search_url(self, keyword, page):
        self._current_keyword = keyword or ""
        if page != 1:
            return None
        sitemap_list = await self._discover_news_sitemaps()
        batches = await asyncio.gather(
            *(self._fetch_sitemap_entries(url) for url in sitemap_list)
        )
        return [entry for batch in batches for entry in batch]

    def parse_article_links(self, response_text_or_entries):
        """Accept either raw XML (legacy) or pre-parsed list of (loc, title)."""
        if not response_text_or_entries:
            return None
        if isinstance(response_text_or_entries, str):
            entries = self._parse_sitemap_xml(response_text_or_entries)
        else:
            entries = response_text_or_entries

        tokens = _keyword_tokens(self._current_keyword)
        links = []
        seen = set()
        for loc, title in entries:
            if not _is_canonical_article(loc):
                continue
            haystack = _normalize(f"{title} {loc}")
            if not _matches_all_tokens(haystack, tokens):
                continue
            if loc not in seen:
                links.append(loc)
                seen.add(loc)
            if len(links) >= self.MAX_ARTICLES_PER_QUERY:
                break
        return links or None

    # ------------------------------------------------------------------
    # Latest path: unfiltered sitemap entries
    # ------------------------------------------------------------------
    async def build_latest_url(self, page):
        sitemap_list = await self._discover_news_sitemaps()
        sitemap_url = self._sitemap_for_page(page, sitemap_list)
        if not sitemap_url:
            return None
        return await self._fetch_sitemap_entries(sitemap_url)

    def parse_latest_article_links(self, response_text_or_entries):
        if not response_text_or_entries:
            return None
        if isinstance(response_text_or_entries, str):
            entries = self._parse_sitemap_xml(response_text_or_entries)
        else:
            entries = response_text_or_entries

        links = []
        seen = set()
        for loc, _title in entries:
            if not _is_canonical_article(loc):
                continue
            if loc not in seen:
                links.append(loc)
                seen.add(loc)
            if len(links) >= self.MAX_ARTICLES_PER_QUERY:
                break
        return links or None

    # ------------------------------------------------------------------
    # Article fetch + extraction
    # ------------------------------------------------------------------
    async def get_article(self, link, keyword):
        if not _is_canonical_article(link):
            logging.debug("IDXChannel rejecting non-canonical URL: %s", link)
            return

        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("IDXChannel no response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            return

        publish_date = self._extract_date(soup)
        if not publish_date:
            return
        publish_date = _to_naive(publish_date)

        if self.start_date and publish_date < self._normalize_start(self.start_date):
            self.continue_scraping = False
            return

        author = self._extract_author(soup)
        category = self._extract_category(soup, link)
        content = self._extract_content(soup)
        if not content:
            return

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": self.SOURCE_LABEL,
            "link": link,
        }
        await self.queue_.put(item)

    @staticmethod
    def _extract_title(soup):
        meta = soup.find("meta", {"property": "og:title"})
        if meta and meta.get("content"):
            value = meta["content"].strip()
            if value:
                return value
        h1 = soup.select_one("h1")
        if h1:
            value = h1.get_text(strip=True)
            if value:
                return value
        if soup.title and soup.title.string:
            value = soup.title.string.strip()
            if value:
                return value
        return ""

    def _extract_date(self, soup):
        # JSON-LD first
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload = self._parse_ld_json(script.string)
            if not payload:
                continue
            for node in self._iter_ld_nodes(payload):
                dt = node.get("datePublished") or node.get("dateCreated")
                if dt:
                    parsed = self.parse_date(dt)
                    if parsed:
                        return parsed

        # Visible DD/MM/YYYY HH:MM WIB block in the article header.
        for node in soup.select(".article--creator .text-body--2"):
            text = node.get_text(" ", strip=True)
            m = re.search(r"\b\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s+WIB\b", text)
            if m:
                parsed = self._parse_id_date(m.group(0))
                if parsed:
                    return parsed

        # Last-resort regex on full visible text.
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s+WIB\b", text)
        if m:
            parsed = self._parse_id_date(m.group(0))
            if parsed:
                return parsed

        return None

    @staticmethod
    def _parse_id_date(raw):
        # "DD/MM/YYYY HH:MM WIB" → naive datetime.
        try:
            return datetime.strptime(raw, "%d/%m/%Y %H:%M WIB")
        except ValueError:
            return None

    @staticmethod
    def _parse_ld_json(raw):
        if not raw:
            return None
        try:
            import json

            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _iter_ld_nodes(payload):
        if payload is None:
            return
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph") or [node]
            for entry in graph:
                if isinstance(entry, dict):
                    yield entry

    def _extract_author(self, soup):
        # Preferred: the inline creator author link in the article header.
        creator = soup.select_one(".article--creator a.creator")
        if creator:
            text = creator.get_text(" ", strip=True)
            if text:
                return text

        names = []
        for block in soup.select(".tim_editor a.list-tim-editor, a.list-tim-editor"):
            name_el = block.select_one(".name-editor")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name:
                continue
            job_el = block.select_one(".job-editor")
            role = job_el.get_text(strip=True).lower() if job_el else ""
            if "reporter" in role:
                return name
            if name not in names:
                names.append(name)
        if names:
            return ", ".join(names)

        meta = soup.find("meta", {"name": "author"})
        if meta and meta.get("content"):
            value = meta["content"].strip()
            if value:
                return value
        return "Unknown"

    def _extract_category(self, soup, link):
        # Breadcrumb link in the article header (first anchor in .article--creator).
        creator = soup.select_one(".article--creator")
        if creator:
            anchor = creator.find("a", href=True)
            if anchor:
                text = anchor.get_text(strip=True)
                if text:
                    return text

        # Fallback: first path segment of the canonical URL.
        parsed = urlparse(link)
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return parts[0]
        return "news"

    def _extract_content(self, soup):
        body = soup.select_one(".article--content")
        if not body:
            body = soup.select_one("article")
        if not body:
            return ""

        for tag in list(body.find_all(["script", "style", "iframe", "noscript"])):
            tag.extract()
        for tag in list(body.find_all(attrs={"class": _NOISE_CLASS_RE})):
            tag.extract()
        for tag in list(body.select(".baca-juga-new, .baca_juga, #relatedNews, .berita--terkait")):
            tag.extract()

        paragraphs = []
        for p in body.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) >= 30:
                paragraphs.append(text)
        content = " ".join(paragraphs).strip()
        if content:
            return content
        return body.get_text(" ", strip=True)

    @staticmethod
    def _normalize_start(value):
        if value is None:
            return None
        if hasattr(value, "tzinfo") and value.tzinfo is not None:
            try:
                return value.replace(tzinfo=None)
            except (AttributeError, ValueError):
                return value
        return value