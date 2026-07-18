"""Indopolitika HTML search, index, and article scraper."""

import contextvars
import json
import logging
import re
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


BASE_URL = "https://indopolitika.com"
SOURCE_LABEL = "indopolitika.com"
MAX_SEARCH_PAGES = 10
_current_keyword: contextvars.ContextVar[str] = contextvars.ContextVar(
    "indopolitika_current_keyword", default=""
)

_CARD_LINK_SELECTOR = (
    ".widget.indeks .widget-box .media.media-item "
    "h2.media-title a.media-link[href]"
)
_EXCLUDED_ROOT_PATHS = {
    "about",
    "author",
    "category",
    "comments",
    "contact",
    "disclaimer",
    "feed",
    "indeks-berita",
    "kontak",
    "page",
    "pedoman-media-siber",
    "privacy-policy",
    "redaksi",
    "search",
    "sitemap",
    "tag",
    "tentang-kami",
    "wp-admin",
    "wp-content",
    "wp-includes",
    "wp-json",
}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$", re.IGNORECASE)
_NOISE_RE = re.compile(
    r"promo|advert|(^|[-_ ])ads?([-_ ]|$)|google-auto-placed|related|"
    r"baca[-_ ]?juga|recommend|sidebar|share|social|newsletter|subscribe|"
    r"buttonOnGooglePill|teks-dalam-kotak",
    re.IGNORECASE,
)

def _matches_keyword(keyword, title):
    tokens = [token for token in re.split(r"\W+", (keyword or "").casefold()) if token]
    haystack = (title or "").casefold()
    return all(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)



class IndopolitikaScraper(BaseScraper):
    """Collect canonical articles from Indopolitika's native HTML pages."""

    BASE_URL = BASE_URL
    SOURCE_LABEL = SOURCE_LABEL
    MAX_SEARCH_PAGES = MAX_SEARCH_PAGES
    @property
    def _current_keyword(self):
        return _current_keyword.get()

    @_current_keyword.setter
    def _current_keyword(self, value):
        _current_keyword.set(value)


    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = BASE_URL
        self.start_date = start_date
        self.max_latest_pages = MAX_SEARCH_PAGES
        self._current_keyword = self.keywords[0] if len(self.keywords) == 1 else ""
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def build_search_url(self, keyword, page):
        if page < 1 or page > MAX_SEARCH_PAGES:
            return None
        self._current_keyword = keyword
        encoded = quote(keyword, safe="")
        path = f"/?s={encoded}" if page == 1 else f"/page/{page}/?s={encoded}"
        return await self.fetch(f"{BASE_URL}{path}", headers=self.headers, timeout=30)

    async def build_latest_url(self, page):
        if page < 1 or page > self.max_latest_pages:
            return None
        path = "/indeks-berita/" if page == 1 else f"/indeks-berita/page/{page}/"
        return await self.fetch(f"{BASE_URL}{path}", headers=self.headers, timeout=30)

    def parse_article_links(self, response_text, keyword=None):
        active_keyword = self._current_keyword if keyword is None else keyword
        return self._collect_card_links(response_text, active_keyword)

    def parse_latest_article_links(self, response_text):
        return self._collect_card_links(response_text)

    @staticmethod
    def _collect_card_links(response_text, keyword=""):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = []
        seen = set()
        for anchor in soup.select(_CARD_LINK_SELECTOR):
            if keyword and not _matches_keyword(keyword, anchor.get_text(" ", strip=True)):
                continue
            link = IndopolitikaScraper._canonical_article_url(anchor.get("href", ""))
            if link and link not in seen:
                seen.add(link)
                links.append(link)
        return links or None

    @staticmethod
    def _canonical_article_url(href):
        if not isinstance(href, str) or not href.strip():
            return None
        parsed = urlparse(urljoin(f"{BASE_URL}/", href.strip()))
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "indopolitika.com":
            return None
        if parsed.params or parsed.query or parsed.fragment:
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 1:
            return None
        slug = parts[0]
        if slug.lower() in _EXCLUDED_ROOT_PATHS or not _SLUG_RE.fullmatch(slug):
            return None
        return f"{BASE_URL}/{slug}/"

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("Indopolitika empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")
        title = self._extract_title(soup)
        publish_date = self._extract_date(soup)
        content = self._extract_content(soup)
        if not title or not publish_date or not content:
            logging.warning("Indopolitika incomplete article: %s", link)
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        await self.queue_.put(
            {
                "title": title,
                "publish_date": publish_date,
                "author": self._extract_author(soup),
                "content": content,
                "keyword": keyword,
                "category": self._extract_category(soup),
                "source": SOURCE_LABEL,
                "link": link,
            }
        )

    @staticmethod
    def _extract_title(soup):
        title = soup.select_one(".post-title h1")
        return title.get_text(" ", strip=True) if title else ""

    def _extract_date(self, soup):
        for node in self._json_ld_objects(soup):
            raw = node.get("datePublished")
            if raw:
                parsed = self.parse_date(str(raw))
                if parsed:
                    return parsed
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            return self.parse_date(meta["content"])
        return None

    @staticmethod
    def _extract_author(soup):
        author = soup.select_one(".post-authorname a")
        if author:
            value = author.get_text(" ", strip=True)
            if value:
                return value
        return "Unknown"

    @classmethod
    def _extract_category(cls, soup):
        for node in cls._json_ld_objects(soup):
            section = node.get("articleSection")
            if isinstance(section, list):
                for entry in section:
                    if isinstance(entry, str) and entry.strip():
                        return entry.strip()
            elif isinstance(section, str) and section.strip():
                return section.strip()

        breadcrumb = soup.select_one(
            ".post-breadcrumb, .breadcrumb, nav[aria-label*='breadcrumb' i]"
        )
        if breadcrumb:
            values = [
                item.get_text(" ", strip=True)
                for item in breadcrumb.select("a, span")
                if item.get_text(" ", strip=True).lower() not in {"", "home"}
            ]
            if values:
                return values[-1]
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        body = soup.select_one(
            ".post-body.post-article, .post-body .post-content .post-article, "
            ".post-content .post-article"
        )
        if not body:
            return ""
        for tag in body.select("script, style, noscript, iframe, figure, ins"):
            if tag.attrs is not None:
                tag.decompose()
        for tag in list(body.find_all(True)):
            if tag.attrs is None:
                continue
            marker = " ".join(
                [str(tag.get("id") or ""), *[str(value) for value in (tag.get("class") or [])]]
            )
            if marker and _NOISE_RE.search(marker):
                tag.decompose()
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in body.find_all("p")
            if paragraph.get_text(" ", strip=True)
        ]
        return re.sub(r"\s+", " ", " ".join(paragraphs)).strip()

    @staticmethod
    def _json_ld_objects(soup):
        objects = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                graph = candidate.get("@graph")
                if isinstance(graph, list):
                    objects.extend(node for node in graph if isinstance(node, dict))
                objects.append(candidate)
        return objects
