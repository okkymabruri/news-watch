"""
NBC News (nbcnews.com) scraper — monthly archive for search, news sitemap for latest.

Verified endpoints (2026-07-27):
    archive: https://www.nbcnews.com/archive/articles/<year>/<month-name>
             one page per calendar month, ~1200 anchors under a single
             .MonthPage container, each anchor's text is the headline;
             no pagination
    latest:  https://www.nbcnews.com/sitemap/nbcnews/sitemap-news
             (urlset, ~53 entries, <news:title> + <news:publication_date>)
    article: https://www.nbcnews.com/<section>/.../<slug>-rcna<digits>

robots.txt disallows /search and /pages/search/, so keyword search filters the
monthly archive instead. Unlike the other feed-filtering adapters this gives
real historical reach -- the archive is addressable by month for years back --
so the search path walks the months spanned by start_date rather than a single
recent window.

Two paths are deliberately not used: https://www.nbcnews.com/sitemap.xml is
blocked (only the paths robots advertises respond), and
feeds.nbcnews.com/nbcnews/public/news mixes today.com links and a bare
homepage link, which would put the wrong value in the source field.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

_SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_NSMAP = {"sm": _SM_NS, "news": _NEWS_NS}

_BASE_URL = "https://www.nbcnews.com"
_LATEST_SITEMAP_URL = f"{_BASE_URL}/sitemap/nbcnews/sitemap-news"

_ALLOWED_HOSTS = ("nbcnews.com", "www.nbcnews.com")

# Canonical article slugs end in -rcna<digits>.
_ARTICLE_ID_RE = re.compile(r"-rcna\d+/?$", re.IGNORECASE)

# Live blogs re-publish under one URL with a stale datePublished, and
# video/photo surfaces carry no story text.
_NON_ARTICLE_RE = re.compile(r"/(?:live-blog|video|videos|photos)(?:/|$)", re.IGNORECASE)

_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
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


def _is_article_url(url):
    if not url:
        return False
    parsed = urlparse(url)
    if (parsed.netloc or "").lower() not in _ALLOWED_HOSTS:
        return False
    if _NON_ARTICLE_RE.search(parsed.path):
        return False
    return bool(_ARTICLE_ID_RE.search(parsed.path))


def _months_descending(start, end):
    """(year, month) pairs from `end` back to `start`, newest first."""
    months = []
    year, month = end.year, end.month
    while (year, month) >= (start.year, start.month):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


class NBCNewsScraper(BaseScraper):
    """NBC News adapter: monthly archive pages for search, news sitemap for latest."""

    BASE_URL = _BASE_URL
    LATEST_SITEMAP_URL = _LATEST_SITEMAP_URL
    SOURCE_LABEL = "nbcnews.com"
    MAX_ARTICLES_PER_QUERY = 25
    # Archive pages are ~3 MB each; bound how far one run will walk back.
    MAX_MONTHS = 12

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = self.BASE_URL
        self.start_date = start_date
        self._current_keyword = ""
        self.headers = {"Accept-Language": "en-US,en;q=0.9"}

    # ------------------------------------------------------------------
    # Month planning
    # ------------------------------------------------------------------
    def _months(self):
        """Months to walk, newest first. Without start_date, the current month only."""
        now = datetime.now()
        start = self.start_date or now
        return _months_descending(start, now)[: self.MAX_MONTHS]

    def archive_url(self, year, month):
        return f"{self.BASE_URL}/archive/articles/{year}/{_MONTH_NAMES[month - 1]}"

    # ------------------------------------------------------------------
    # Archive parsing
    # ------------------------------------------------------------------
    @staticmethod
    def parse_archive_entries(response_text):
        """Return [(url, headline)] from a monthly archive page."""
        if not response_text:
            return []
        soup = BeautifulSoup(response_text, "html.parser")
        entries = []
        seen = set()
        for anchor in soup.select(".MonthPage a[href]"):
            href = (anchor.get("href") or "").strip()
            if href.startswith("/"):
                href = f"{_BASE_URL}{href}"
            if not _is_article_url(href) or href in seen:
                continue
            entries.append((href, anchor.get_text(" ", strip=True)))
            seen.add(href)
        return entries

    def _select(self, entries, tokens):
        links = []
        for url, headline in entries:
            if tokens and not _matches_all_tokens(
                _normalize(f"{headline} {url}"), tokens
            ):
                continue
            links.append(url)
            if len(links) >= self.MAX_ARTICLES_PER_QUERY:
                break
        return links or None

    # ------------------------------------------------------------------
    # Search path: one archive month per page
    # ------------------------------------------------------------------
    async def build_search_url(self, keyword, page):
        self._current_keyword = keyword or ""
        months = self._months()
        if page < 1 or page > len(months):
            return None
        year, month = months[page - 1]
        return await self.fetch(
            self.archive_url(year, month), headers=self.headers, timeout=45
        )

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        entries = self.parse_archive_entries(response_text)
        return self._select(entries, _keyword_tokens(self._current_keyword))

    async def fetch_search_results(self, keyword):
        """Walk every planned month.

        BaseScraper's page loop stops at the first page that yields no links,
        which here would mean one keyword-less month hides every older month
        behind it. Months are independent, so iterate them all and only stop on
        the per-keyword article cap.
        """
        self._current_keyword = keyword or ""
        tokens = _keyword_tokens(keyword)
        collected = 0
        found_any = False

        for year, month in self._months():
            if not self.continue_scraping:
                break
            response_text = await self.fetch(
                self.archive_url(year, month), headers=self.headers, timeout=45
            )
            if not response_text:
                continue

            links = self._select(self.parse_archive_entries(response_text), tokens)
            if not links:
                continue

            found_any = True
            remaining = self.MAX_ARTICLES_PER_QUERY - collected
            links = links[:remaining]
            collected += len(links)

            if not await self.process_page(links, keyword):
                break
            if collected >= self.MAX_ARTICLES_PER_QUERY:
                break

        if not found_any:
            logging.info(
                f"No news found on {self.base_url} for keyword: '{keyword}'"
            )

    # ------------------------------------------------------------------
    # Latest path: news sitemap
    # ------------------------------------------------------------------
    async def build_latest_url(self, page):
        if page != 1:
            return None
        return await self.fetch(
            self.LATEST_SITEMAP_URL, headers=self.headers, timeout=30
        )

    @staticmethod
    def parse_sitemap_entries(response_text):
        """Return [(loc, title)] from the news sitemap urlset."""
        if not response_text:
            return []
        head = response_text.lstrip()[:64].lower()
        if not head.startswith("<?xml") and "<urlset" not in head:
            return []
        try:
            root = ET.fromstring(response_text)
        except ET.ParseError as e:
            logging.error("NBC News sitemap parse error: %s", e)
            return []
        if root.tag != f"{{{_SM_NS}}}urlset":
            return []

        entries = []
        for url in root.findall("sm:url", _NSMAP):
            loc = (url.findtext("sm:loc", "", _NSMAP) or "").strip()
            if not loc or not _is_article_url(loc):
                continue
            title = ""
            news = url.find("news:news", _NSMAP)
            if news is not None:
                title = (news.findtext("news:title", "", _NSMAP) or "").strip()
            entries.append((loc, title))
        return entries

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        return self._select(self.parse_sitemap_entries(response_text), [])

    # ------------------------------------------------------------------
    # Article extraction
    # ------------------------------------------------------------------
    async def get_article(self, link, keyword):
        if not _is_article_url(link):
            logging.debug("NBC News rejecting non-article URL: %s", link)
            return

        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("NBC News no response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")
        node = self._news_article_node(soup)

        title = self._extract_title(soup, node)
        if not title:
            return

        publish_date = self._extract_date(soup, node)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            return

        content = self._extract_content(soup)
        if not content:
            return

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": self._extract_author(soup, node),
            "content": content,
            "keyword": keyword,
            "category": self._extract_category(node, link),
            "source": self.SOURCE_LABEL,
            "link": link,
        }
        await self.queue_.put(item)

    @staticmethod
    def _news_article_node(soup):
        import json

        for script in soup.find_all("script", {"type": "application/ld+json"}):
            if not script.string:
                continue
            try:
                payload = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue
            nodes = payload if isinstance(payload, list) else [payload]
            for entry in nodes:
                if not isinstance(entry, dict):
                    continue
                for candidate in entry.get("@graph") or [entry]:
                    if isinstance(candidate, dict) and "Article" in str(
                        candidate.get("@type")
                    ):
                        return candidate
        return None

    @staticmethod
    def _extract_title(soup, node):
        if node and node.get("headline"):
            return str(node["headline"]).strip()
        meta = soup.find("meta", {"property": "og:title"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        if soup.h1:
            return soup.h1.get_text(strip=True)
        return ""

    def _extract_date(self, soup, node):
        if node:
            for key in ("datePublished", "dateCreated", "dateModified"):
                if node.get(key):
                    parsed = self.parse_date(str(node[key]))
                    if parsed:
                        return parsed
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el:
            return self.parse_date(time_el["datetime"])
        return None

    @staticmethod
    def _extract_author(soup, node):
        if node:
            author = node.get("author")
            names = []
            for entry in author if isinstance(author, list) else [author]:
                if isinstance(entry, dict):
                    name = (entry.get("name") or "").strip()
                elif isinstance(entry, str):
                    name = entry.strip()
                else:
                    name = ""
                if name and name not in names:
                    names.append(name)
            if names:
                return ", ".join(names)
        meta = soup.find("meta", {"name": "author"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return "Unknown"

    @staticmethod
    def _extract_category(node, link):
        if node and node.get("articleSection"):
            section = node["articleSection"]
            if isinstance(section, list):
                section = section[0] if section else ""
            if section:
                return str(section).strip()
        parts = [p for p in urlparse(link).path.split("/") if p]
        return parts[0] if parts else "news"

    @staticmethod
    def _extract_content(soup):
        body = soup.select_one("div.article-body__content") or soup.select_one("article")
        if body is None:
            return ""
        for tag in list(
            body.find_all(["script", "style", "iframe", "noscript", "figure", "aside"])
        ):
            tag.extract()
        paragraphs = [
            text
            for p in body.find_all("p")
            if len(text := p.get_text(" ", strip=True)) >= 30
        ]
        content = " ".join(paragraphs).strip()
        return content or body.get_text(" ", strip=True)
