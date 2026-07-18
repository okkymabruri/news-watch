"""
IDN Financials scraper — server-rendered search and listing surfaces.

Site:    https://www.idnfinancials.com/id/
Search:  https://www.idnfinancials.com/id/search?q={keyword}&per_page={page}
Latest:  https://www.idnfinancials.com/id/news
Article: /id/news/{id}/{slug}

Search pages render two regions:
- a `Berita` widget with article cards whose titles are keyword-relevant,
- a sidebar with unrelated current `/id/news/` links that must be filtered out.
Nonsense queries render `Tidak ada data yang ditemukan.`
"""

import contextvars
import json
import logging
import re
from datetime import datetime
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

# Task-local current keyword: each concurrent `fetch_search_results`
# coroutine gets its own context, so keywords cannot trample one another.
_current_keyword: contextvars.ContextVar[str] = contextvars.ContextVar(
    "idnfinancials_current_keyword", default=""
)

BASE_URL = "https://www.idnfinancials.com"
SEARCH_URL = f"{BASE_URL}/id/search"
LATEST_URL = f"{BASE_URL}/id/news"
SOURCE_LABEL = "idnfinancials.com"

# article URL pattern: /id/news/{numeric-id}/{slug}
ARTICLE_RE = re.compile(r"^https?://(www\.)?idnfinancials\.com/id/news/\d+/[A-Za-z0-9\-_/]+/?$")

# result widgets on the search page; the "Berita" widget carries keyword hits.
RESULTS_WIDGET_SELECTOR = ".widget.side-news .widget-body ul.list li.item"
WIDGET_HEADER_SELECTOR = ".widget-header h2"

# nonsense-query marker; site renders this exact string when no matches exist.
NO_RESULT_MARKER = "Tidak ada data yang ditemukan"

# article page selectors.
TITLE_SELECTORS = (
    'meta[property="og:title"]',
    "h2.title",
    "h1",
)
PUBLISHED_META_SELECTORS = (
    'meta[property="article:published_time"]',
    'meta[property="og:article:published_time"]',
    'meta[itemprop="datePublished"]',
)
AUTHOR_META_SELECTORS = (
    'meta[name="author"]',
    'meta[property="article:author"]',
)
SECTION_META_SELECTORS = (
    'meta[property="article:section"]',
)
BODY_SELECTORS = (
    "div.article-body",
    "article",
)
BODY_NOISE_CLASS_RE = re.compile(
    r"baca[_-]juga|related|popular|sidebar|share|social|newsletter|advert|ads|outstream|embed|pagination|footer|header",
    re.IGNORECASE,
)

# tokens shorter than this are ignored when scoring keyword relevance.
_MIN_TOKEN_LEN = 3
# score threshold for accepting a candidate as keyword-relevant.
_RELEVANCE_MIN_TOKENS = 1


def _normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[\s\-_/.,;:!?\"'()\[\]{}]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _keyword_tokens(keyword):
    parts = re.findall(r"[A-Za-z0-9]+", (keyword or "").lower())
    return [p for p in parts if len(p) >= _MIN_TOKEN_LEN]


def _is_relevant(keyword, title_text, url):
    tokens = _keyword_tokens(keyword)
    if not tokens:
        return True
    haystack = _normalize(f"{title_text or ''} {url or ''}")
    if not haystack:
        return False
    return all(re.search(rf"\b{re.escape(tok)}\b", haystack) for tok in tokens)


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        # python's fromisoformat handles "+07:00" offsets in 3.11+
        cleaned = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return None


class IDNFinancialsScraper(BaseScraper):
    """Adapter for idnfinancials.com Indonesian financial news."""
    @property
    def _current_keyword(self):
        return _current_keyword.get()

    @_current_keyword.setter
    def _current_keyword(self, value):
        _current_keyword.set(value)


    def __init__(
        self,
        keywords,
        concurrency=5,
        start_date=None,
        queue_=None,
        max_pages=10,
    ):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = BASE_URL
        self.start_date = start_date
        self.max_pages = max_pages
        # keyword + pagination state live in module-level ContextVars
        # so concurrent fetch_search_results tasks do not clobber each other.
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        self._current_keyword = ""

    # ---------- search ----------

    async def build_search_url(self, keyword, page):
        if page < 1 or page > self.max_pages:
            return None
        url = f"{SEARCH_URL}?q={quote(keyword, safe='')}&per_page={page}"
        self._current_keyword = keyword
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        # explicit no-result gate: site renders this string in a blockquote.
        if NO_RESULT_MARKER in response_text:
            self.continue_scraping = False
            return None

        soup = BeautifulSoup(response_text, "html.parser")

        # locate the "Berita" widget; "Video" widget is unrelated.
        target_items = []
        for widget in soup.select(".widget.side-news"):
            header = widget.select_one(WIDGET_HEADER_SELECTOR)
            header_text = header.get_text(strip=True).lower() if header else ""
            if header_text and header_text != "berita":
                continue
            items = widget.select("ul.list > li.item > a[href]")
            if items:
                target_items = items
                break

        if not target_items:
            return None
        keyword = self._current_keyword
        filtered = []
        seen = set()
        for a in target_items:
            href = a.get("href", "")
            if not href:
                continue
            full_url = urljoin(BASE_URL, href)
            if not ARTICLE_RE.match(full_url):
                continue
            if full_url in seen:
                continue
            seen.add(full_url)
            title = a.get("title") or a.get_text(strip=True)
            if not _is_relevant(keyword, title, full_url):
                logging.debug(
                    "IDNFinancials dropping unrelated candidate for %r: %s",
                    keyword,
                    full_url,
                )
                continue
            filtered.append(full_url)

        return filtered or None

    async def get_article(self, link, keyword):

        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("IDNFinancials no response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        # ---- title (required) ----
        title = ""
        for sel in TITLE_SELECTORS:
            el = soup.select_one(sel)
            if not el:
                continue
            if el.name == "meta":
                title = el.get("content", "").strip()
            else:
                title = el.get_text(strip=True)
            if title:
                break
        if not title:
            logging.error("IDNFinancials title not found | url: %s", link)
            return

        # ---- date (authoritative meta first, then JSON-LD) ----
        publish_date = None
        for sel in PUBLISHED_META_SELECTORS:
            meta = soup.select_one(sel)
            if meta and meta.get("content"):
                publish_date = _parse_iso_datetime(meta["content"])
                if publish_date:
                    break

        if publish_date is None:
            for script in soup.find_all("script", type="application/ld+json"):
                if not script.string:
                    continue
                try:
                    payload = json.loads(script.string)
                except json.JSONDecodeError:
                    continue
                publish_date = self._date_from_jsonld(payload)
                if publish_date:
                    break

        if publish_date is None:
            # last-chance fallback: the data-date attribute on date-published div
            date_div = soup.select_one("div.date-published[data-date]")
            if date_div:
                publish_date = _parse_iso_datetime(date_div.get("data-date"))

        if publish_date is None:
            logging.error("IDNFinancials date parse failed | url: %s", link)
            return

        # ---- date-range filtering ----
        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        # ---- author ----
        author = self._extract_author(soup)
        if not author:
            author = "Unknown"

        # ---- category ----
        category = self._extract_category(soup, link)

        # ---- body ----
        body = self._extract_body(soup)
        if not body:
            logging.warning("IDNFinancials empty body | url: %s", link)
            return

        await self.queue_.put(
            {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": body,
                "keyword": keyword,
                "category": category,
                "source": SOURCE_LABEL,
                "link": link,
            }
        )

    @staticmethod
    def _date_from_jsonld(payload):
        graph = payload.get("@graph") if isinstance(payload, dict) else None
        candidates = []
        if isinstance(graph, list):
            candidates.extend(graph)
        if isinstance(payload, dict):
            candidates.append(payload)
        for node in candidates:
            if not isinstance(node, dict):
                continue
            if node.get("@type") in {"NewsArticle", "Article"}:
                stamp = node.get("datePublished") or node.get("dateCreated")
                parsed = _parse_iso_datetime(stamp) if stamp else None
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _extract_author(soup):
        # JSON-LD preferred; meta tags less reliable on this site.
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                payload = json.loads(script.string)
            except json.JSONDecodeError:
                continue
            graph = payload.get("@graph") if isinstance(payload, dict) else None
            nodes = graph if isinstance(graph, list) else [payload]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                author = node.get("author")
                if isinstance(author, dict):
                    name = author.get("name")
                    if name:
                        return name.strip()
                elif isinstance(author, list) and author:
                    first = author[0]
                    if isinstance(first, dict):
                        name = first.get("name")
                        if name:
                            return name.strip()
                    elif isinstance(first, str):
                        return first.strip()
        for sel in AUTHOR_META_SELECTORS:
            meta = soup.select_one(sel)
            if meta and meta.get("content"):
                content = meta["content"].strip()
                if content and not content.startswith("http"):
                    return content
        # header card fallback
        author_link = soup.select_one(".idn-authors .ia-names a.ian")
        if author_link:
            return author_link.get_text(strip=True)
        return None

    @staticmethod
    def _extract_category(soup, link):
        for sel in SECTION_META_SELECTORS:
            meta = soup.select_one(sel)
            if meta and meta.get("content"):
                return meta["content"].strip()
        if "/id/news/" in link:
            return "Berita"
        return "Unknown"

    @staticmethod
    def _extract_body(soup):
        body_el = None
        for sel in BODY_SELECTORS:
            body_el = soup.select_one(sel)
            if body_el:
                break
        if not body_el:
            return ""

        for tag in body_el.find_all(["script", "style", "noscript", "iframe"]):
            tag.extract()
        for tag in body_el.find_all(
            ["div", "section", "aside", "footer"],
            class_=BODY_NOISE_CLASS_RE,
        ):
            tag.extract()

        paragraphs = []
        for p in body_el.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            if text:
                paragraphs.append(text)
        if not paragraphs:
            return body_el.get_text(separator=" ", strip=True)
        return " ".join(paragraphs)

    # ---------- latest ----------

    async def build_latest_url(self, page):
        if page < 1 or page > self.max_pages:
            return None
        if page == 1:
            url = LATEST_URL
        else:
            url = f"{LATEST_URL}?page={page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            full_url = urljoin(BASE_URL, href)
            if ARTICLE_RE.match(full_url):
                links.add(full_url)
        return links or None
