"""Warta Ekonomi POST-search and `/indeks[/YYYYMMDD]` history scraper.

Search flow: POST `q=<keyword>` to /search → server replies 303 → aiohttp
follows the redirect to /search/{id} which is the result page. Subsequent
pages reuse the captured id with `?page=N`. Nonsense/gibberish queries may
redirect to an id whose page returns HTTP 404/500; fetch() already returns
None in that case so the loop terminates cleanly.

History flow: /indeks/YYYYMMDD paginates with ?page=N (works back to
2025-01-05 at minimum). /indeks (no date) returns today's articles.
"""

import contextvars
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

# Task-local keyword + redirect id; each concurrent fetch_search_results
# coroutine gets its own copy, so six keywords cannot clobber each other.
_current_keyword: contextvars.ContextVar[str] = contextvars.ContextVar(
    "wartaekonomi_current_keyword", default=""
)
_search_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "wartaekonomi_search_id", default=""
)



_BASE_URL = "https://wartaekonomi.co.id"
_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?wartaekonomi\.co\.id/read\d+/[a-z0-9][a-z0-9-]*$",
    re.IGNORECASE,
)
_NOISE_CLASS_RE = re.compile(
    r"adInArticle|baca-juga|related|share|social|sidebar|newsletter|"
    r"advert|(^|[-_ ])ad([-_ ]|$)|banner|comment|articleListShare",
    re.IGNORECASE,
)


def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _keyword_tokens(keyword):
    return [tok for tok in re.split(r"\W+", keyword.lower()) if len(tok) > 1]


def _matches_keyword(title, tokens):
    if not tokens:
        return True
    haystack = _normalize(title)
    if not haystack:
        return False
    return all(re.search(rf"\b{re.escape(tok)}\b", haystack) for tok in tokens)


class WartaEkonomiScraper(BaseScraper):
    """Collect Warta Ekonomi search hits and indeks history."""
    @property
    def _current_keyword(self):
        return _current_keyword.get()

    @_current_keyword.setter
    def _current_keyword(self, value):
        _current_keyword.set(value)

    @property
    def _search_id(self):
        return _search_id.get()

    @_search_id.setter
    def _search_id(self, value):
        _search_id.set(value)


    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = _BASE_URL
        self.start_date = start_date
        self.continue_scraping = True
        self.max_latest_pages = 1
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"{_BASE_URL}/",
        }
        self._current_keyword = ""
        self._search_id = ""

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def build_search_url(self, keyword, page):
        if page < 1:
            page = 1

        if page == 1:
            # aiohttp follows the 303 -> /search/{id} transparently and
            # returns the resolved HTML body. We capture the {id} from the
            # returned markup on the next call (page 2).
            self._search_id = ""
            return await self.fetch(
                f"{_BASE_URL}/search",
                method="POST",
                data={"q": keyword},
                headers=self.headers,
                timeout=30,
            )

        search_id = self._search_id
        if not search_id:
            return None
        url = f"{_BASE_URL}/search/{search_id}?page={page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")

        # Capture the resolved search id from any pagination anchor so
        # subsequent pages can hit /search/{id}?page=N directly.
        if not self._search_id:
            for anchor in soup.select('a[href*="/search/"]'):
                href = anchor.get("href", "")
                m = re.search(r"/search/(\d+)", href)
                if m:
                    self._search_id = m.group(1)
                    break

        links = set()
        tokens = _keyword_tokens(self._current_keyword)
        for anchor in soup.select("a.articleListItem[href]"):
            href = anchor.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE_URL, href)
            if not _ARTICLE_RE.match(full):
                continue
            title = anchor.get("title") or anchor.get_text(" ", strip=True)
            if not _matches_keyword(title, tokens):
                continue
            links.add(full)
        return links or None

    async def fetch_search_results(self, keyword):
        self._current_keyword = keyword
        await super().fetch_search_results(keyword)

    # ------------------------------------------------------------------
    # Latest / history
    # ------------------------------------------------------------------
    async def build_latest_url(self, page):
        if page < 1:
            page = 1
        url = self._indeks_url()
        if page > 1:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}page={page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for anchor in soup.select("a.articleListItem[href]"):
            href = anchor.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE_URL, href)
            if _ARTICLE_RE.match(full):
                links.add(full)
        return links or None

    def _indeks_url(self):
        if self.start_date:
            stamp = self._date_token(self.start_date)
            if stamp:
                return f"{_BASE_URL}/indeks/{stamp}"
        return f"{_BASE_URL}/indeks"

    @staticmethod
    def _date_token(value):
        if isinstance(value, datetime):
            return value.strftime("%Y%m%d")
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y%m%d")
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------
    # Article extraction
    # ------------------------------------------------------------------
    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("Warta Ekonomi empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")
        title = self._extract_title(soup)
        publish_date = self._extract_date(soup)
        content = self._extract_content(soup)
        if not title or not publish_date or not content:
            logging.warning("Warta Ekonomi incomplete article: %s", link)
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        canonical = self._extract_canonical(soup, link)
        category = self._extract_category(soup, canonical)
        author = self._extract_author(soup)

        await self.queue_.put({
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "wartaekonomi.co.id",
            "link": canonical,
        })

    @staticmethod
    def _extract_title(soup):
        heading = soup.select_one("article h1, .articlePostHeader h1")
        if heading:
            text = heading.get_text(" ", strip=True)
            if text:
                return text
        meta = soup.select_one('meta[property="og:title"]')
        return meta.get("content", "").strip() if meta else ""

    def _extract_date(self, soup):
        for data in self._json_ld_objects(soup):
            raw = data.get("datePublished") or data.get("dateCreated")
            if raw:
                parsed = self.parse_date(str(raw))
                if parsed:
                    return parsed

        meta = soup.select_one(
            'meta[property="article:published_time"], '
            'meta[itemprop="datePublished"]'
        )
        if meta and meta.get("content"):
            parsed = self.parse_date(meta["content"])
            if parsed:
                return parsed

        time_tag = soup.select_one("time[datetime]")
        if time_tag:
            parsed = self.parse_date(time_tag["datetime"])
            if parsed:
                return parsed
            visible = time_tag.get_text(" ", strip=True)
            parsed = self.parse_date(visible, languages=["id"])
            if parsed:
                return parsed
        return None

    @classmethod
    def _extract_author(cls, soup):
        for data in cls._json_ld_objects(soup):
            author = data.get("author")
            if isinstance(author, dict):
                name = author.get("name")
                if name:
                    return str(name).strip()
            if isinstance(author, list):
                for entry in author:
                    if isinstance(entry, dict) and entry.get("name"):
                        return str(entry["name"]).strip()
        meta = soup.select_one('meta[name="author"], meta[property="article:author"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        return "Unknown"

    @classmethod
    def _extract_category(cls, soup, link):
        for data in cls._json_ld_objects(soup):
            section = data.get("articleSection")
            if isinstance(section, list) and section:
                return str(section[0]).strip()
            if section:
                return str(section).strip()

        crumbs = soup.select(".articlePostHeader ul li a[href]")
        if crumbs:
            leaf = crumbs[-1].get_text(" ", strip=True)
            if leaf:
                return leaf

        for selector in (
            'meta[property="article:section"]',
            'meta[name="category"]',
        ):
            meta = soup.select_one(selector)
            if meta and meta.get("content"):
                return meta["content"].strip()

        # Real article URLs are /read{n}/{slug}; the path segments there are
        # the article id and the slug, never a category. Short-circuit so we
        # don't emit the slug as a category.
        segments = [seg for seg in urlparse(link).path.split("/") if seg]
        if segments and re.match(r"^read\d+$", segments[0]):
            return "Unknown"
        parts = [
            part
            for part in segments
            if part
            and not part.startswith("category-")
            and not re.match(r"^read\d+$", part)
            and part not in {"news", "ekbis"}
        ]
        if parts:
            return parts[-1]
        return "Unknown"

    @staticmethod
    def _extract_canonical(soup, link):
        meta = soup.select_one(
            'link[rel="canonical"], meta[property="og:url"]'
        )
        if meta:
            value = meta.get("href") or meta.get("content", "")
            value = (value or "").strip()
            if value:
                return value
        return link

    @staticmethod
    def _extract_content(soup):
        body = soup.select_one(".articlePostContent")
        if not body:
            return ""

        for tag in body.find_all(
            ["script", "style", "iframe", "aside", "nav", "form", "ins", "button"]
        ):
            tag.decompose()
        for tag in body.find_all(True, {"class": _NOISE_CLASS_RE}):
            tag.decompose()
        # Warta Ekonomi tags "Baca Juga" inline cross-promo anchors
        for tag in body.find_all("a", string=re.compile(r"^Baca Juga", re.IGNORECASE)):
            tag.decompose()

        paragraphs = []
        for node in body.find_all(["p", "h2", "h3", "li"]):
            text = node.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        return re.sub(r"\s+", " ", " ".join(paragraphs)).strip()

    @staticmethod
    def _json_ld_objects(soup):
        objects = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = data if isinstance(data, list) else [data]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                graph = candidate.get("@graph")
                if isinstance(graph, list):
                    objects.extend(item for item in graph if isinstance(item, dict))
                objects.append(candidate)
        return objects