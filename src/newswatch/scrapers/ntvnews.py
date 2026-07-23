"""
NTVNews.id (www.ntvnews.id) scraper — single Google News sitemap driven.

Verified endpoints:
    news sitemap: https://www.ntvnews.id/sitemap-news.xml
    article:      https://www.ntvnews.id/<category>/<8-digit-id>/<slug>

The site's /search/?q= endpoint is disallowed by robots.txt, so search uses
the bounded news sitemap set instead. Sitemap entries carry <news:title> plus
<news:publication_date> and a <keywords> element; search applies every-token
matching to the title only, in keeping with native search rank by headline.
Latest mode walks the same sitemap without keyword filtering.

Publisher legitimacy (Dewan Pers verified 2024-11-25) is validated separately;
this scraper only consumes the public news sitemap and article markup.
"""
import contextvars
import json
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

_SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_SITEMAP_NSMAP = {"sm": _SM_NS, "news": _NEWS_NS}

_BASE_URL = "https://www.ntvnews.id"
_NEWS_SITEMAP_URL = f"{_BASE_URL}/sitemap-news.xml"

_current_keyword: contextvars.ContextVar[str] = contextvars.ContextVar(
    "ntvnews_current_keyword", default=""
)

_CANONICAL_HOSTS = {"ntvnews.id", "www.ntvnews.id"}
_EXCLUDED_CATEGORIES = {
    "admin", "amp", "author", "category", "feed", "page", "search", "tag", "wp-admin", "wp-content"
}

_NOISE_CLASS_RE = re.compile(
    r"baca[_-]juga|berita[_-]terkait|berita[_-]rekomendasi|share|"
    r"social|sidebar|footer|nav|promo|ads|advert|comment|newsletter|"
    r"recommended|related|tag|topic",
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


def _canonical_article_url(url):
    """Normalize same-site article URLs and reject non-article surfaces."""
    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in _CANONICAL_HOSTS:
        return None
    if parsed.query or parsed.fragment:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3:
        return None
    category, article_id, slug = parts
    if category.lower() in _EXCLUDED_CATEGORIES:
        return None
    if not re.fullmatch(r"[a-z][a-z0-9-]*", category, re.IGNORECASE):
        return None
    if not re.fullmatch(r"\d{8}", article_id):
        return None
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug, re.IGNORECASE):
        return None
    return f"{_BASE_URL}/{category}/{article_id}/{slug}"


class NTVNewsScraper(BaseScraper):
    """NTVNews.id scraper driven by the single Google News sitemap."""

    BASE_URL = _BASE_URL
    SITEMAP_URL = _NEWS_SITEMAP_URL
    SOURCE_LABEL = "ntvnews.id"

    @property
    def _current_keyword(self):
        return _current_keyword.get()

    @_current_keyword.setter
    def _current_keyword(self, value):
        _current_keyword.set(value)
    MAX_ARTICLES_PER_QUERY = 50

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = self.BASE_URL
        self.start_date = start_date
        self.max_latest_pages = 1
        self._current_keyword = self.keywords[0] if len(self.keywords) == 1 else ""
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
    @staticmethod
    def _parse_sitemap_xml(response_text):
        """Return list of (loc, news_title, publication_date) tuples from the
        Google News sitemap urlset.

        The News sitemap is bounded: every <url> is a recent news article, so
        preservation of sitemap order is the natural latest-ranking order.
        """
        if not response_text:
            return []
        head = response_text.lstrip()[:64].lower()
        if not head.startswith("<?xml") and "<urlset" not in head:
            return []
        try:
            root = ET.fromstring(response_text)
        except ET.ParseError as e:
            logging.error("NTVNews sitemap parse error: %s", e)
            return []
        if root.tag != f"{{{_SM_NS}}}urlset":
            return []

        entries = []
        for url in root.findall("sm:url", _SITEMAP_NSMAP):
            loc_el = url.find("sm:loc", _SITEMAP_NSMAP)
            loc = (loc_el.text or "").strip() if loc_el is not None else ""
            if not loc:
                continue
            canonical = _canonical_article_url(loc)
            if not canonical:
                continue
            title = ""
            news_el = url.find("news:news", _SITEMAP_NSMAP)
            if news_el is not None:
                title_el = news_el.find("news:title", _SITEMAP_NSMAP)
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()
            date_text = ""
            if news_el is not None:
                date_el = news_el.find("news:publication_date", _SITEMAP_NSMAP)
                if date_el is not None and date_el.text:
                    date_text = date_el.text.strip()
            entries.append((canonical, title, date_text))
        return entries

    async def _fetch_sitemap_entries(self, sitemap_url):
        text = await self.fetch(sitemap_url, headers=self.headers, timeout=30)
        if not text:
            return []
        return self._parse_sitemap_xml(text)

    # ------------------------------------------------------------------
    # Search path: keyword-filtered sitemap entries (title-only)
    # ------------------------------------------------------------------
    async def build_search_url(self, keyword, page):
        self._current_keyword = keyword or ""
        if page != 1:
            return None
        return await self._fetch_sitemap_entries(self.SITEMAP_URL)

    def parse_article_links(self, response_text_or_entries):
        """Accept either raw XML (legacy) or pre-parsed list of (loc, title, date)."""
        if not response_text_or_entries:
            return None
        if isinstance(response_text_or_entries, str):
            entries = self._parse_sitemap_xml(response_text_or_entries)
        else:
            entries = response_text_or_entries

        tokens = _keyword_tokens(self._current_keyword)
        links = []
        seen = set()
        for loc, title, _date in entries:
            canonical = _canonical_article_url(loc)
            if not canonical:
                continue
            haystack = _normalize(title)
            if not _matches_all_tokens(haystack, tokens):
                continue
            if canonical not in seen:
                links.append(canonical)
                seen.add(canonical)
            if len(links) >= self.MAX_ARTICLES_PER_QUERY:
                break
        return links or None

    # ------------------------------------------------------------------
    # Latest path: unfiltered sitemap entries
    # ------------------------------------------------------------------
    async def build_latest_url(self, page):
        if page != 1:
            return None
        return await self._fetch_sitemap_entries(self.SITEMAP_URL)

    def parse_latest_article_links(self, response_text_or_entries):
        if not response_text_or_entries:
            return None
        if isinstance(response_text_or_entries, str):
            entries = self._parse_sitemap_xml(response_text_or_entries)
        else:
            entries = response_text_or_entries

        links = []
        seen = set()
        for loc, _title, _date in entries:
            canonical = _canonical_article_url(loc)
            if not canonical:
                continue
            if canonical not in seen:
                links.append(canonical)
                seen.add(canonical)
        return links or None

    # ------------------------------------------------------------------
    # Article fetch + extraction
    # ------------------------------------------------------------------
    async def get_article(self, link, keyword):
        canonical = _canonical_article_url(link)
        if not canonical:
            logging.debug("NTVNews rejecting non-canonical URL: %s", link)
            return

        response_text = await self.fetch(canonical, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("NTVNews no response for %s", link)
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
            "link": canonical,
        }
        await self.queue_.put(item)

    @staticmethod
    def _extract_title(soup):
        h1 = soup.select_one("h1.title")
        if h1:
            value = h1.get_text(" ", strip=True)
            if value:
                return value
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
        # JSON-LD NewsArticle first; trusted schema.org metadata.
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

        # visible date strings — NTV often renders DD/MM/YYYY HH:MM
        text = soup.get_text(" ", strip=True)
        for pattern in (
            r"\b\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\b",
            r"\b\d{2}/\d{2}/\d{4}\b",
            r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",
        ):
            m = re.search(pattern, text)
            if m:
                parsed = self.parse_date(m.group(0))
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _parse_ld_json(raw):
        if not raw:
            return None
        try:
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
        candidates = []
        for block in soup.select(".penulis"):
            name = block.select_one(".nama")
            if not name:
                continue
            value = name.get_text(" ", strip=True)
            role = " ".join(
                node.get_text(" ", strip=True) for node in block.select(".detail")
            ).casefold()
            if value:
                candidates.append((value, role))
        for value, role in candidates:
            if "penulis" in role:
                return value

        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload = self._parse_ld_json(script.string)
            for node in self._iter_ld_nodes(payload):
                author = node.get("author")
                authors = author if isinstance(author, list) else [author]
                for entry in authors:
                    if isinstance(entry, dict) and entry.get("name"):
                        return entry["name"].strip()
                    if isinstance(entry, str) and entry.strip():
                        return entry.strip()

        for value, role in candidates:
            if "editor" in role:
                return value
        if candidates:
            return candidates[0][0]
        meta = soup.find("meta", {"name": "author"})
        return meta["content"].strip() if meta and meta.get("content") else "Unknown"

    def _extract_category(self, soup, link):
        breadcrumbs = [
            anchor.get_text(" ", strip=True)
            for anchor in soup.select(".breadcrumb a, nav.breadcrumb a, ol.breadcrumb a")
        ]
        categories = [value for value in breadcrumbs if value and value.casefold() != "home"]
        if categories:
            return categories[-1]
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload = self._parse_ld_json(script.string)
            for node in self._iter_ld_nodes(payload):
                section = node.get("articleSection")
                if isinstance(section, str) and section.strip():
                    return section.strip()
        parts = [part for part in urlparse(link).path.split("/") if part]
        return parts[0] if parts else "news"

    def _extract_content(self, soup):
        body = soup.select_one(".article-content")
        if not body:
            return ""

        for tag in list(body.find_all(["script", "style", "iframe", "noscript"])):
            tag.extract()
        for tag in list(body.find_all(attrs={"class": _NOISE_CLASS_RE})):
            tag.extract()
        for tag in list(body.select(".baca-juga, .baca_juga, #relatedNews, .berita--terkait")):
            tag.extract()
        for p in list(body.find_all("p")):
            if re.match(r"^\s*(?:baca\s+juga|simak\s+juga)\s*:", p.get_text(" ", strip=True), re.IGNORECASE):
                p.extract()

        paragraphs = []
        for p in body.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) >= 20:
                paragraphs.append(text)
        content = " ".join(paragraphs).strip()
        if content:
            return content
        return ""

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
