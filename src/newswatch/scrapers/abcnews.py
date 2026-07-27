"""
ABC News (abcnews.com) scraper — news-sitemap driven.

Verified endpoints (2026-07-27):
    feed:    https://abcnews.com/xmlLatestStories   (urlset, 1000 entries,
             ~13-day window, each with <loc>, <lastmod>, <news:title> and
             <news:publication_date>)
    article: https://abcnews.com/<Section>/<kind>/<slug>-<id>

abcnews.go.com issues a 301 to abcnews.com, so the canonical host is
abcnews.com. robots.txt disallows /search?searchtext=*, so keyword search
filters the news sitemap rather than hitting the site's search endpoint —
the same approach detik and idxchannel take. Because the feed carries a
publication date per entry, the start_date cutoff is applied before any
article is fetched.
"""
import re
import xml.etree.ElementTree as ET
import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

_SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_NSMAP = {"sm": _SM_NS, "news": _NEWS_NS}

_BASE_URL = "https://abcnews.com"
_FEED_URL = f"{_BASE_URL}/xmlLatestStories"

_ALLOWED_HOSTS = ("abcnews.com", "www.abcnews.com", "abcnews.go.com")

# Section landing pages and non-article surfaces carry no story body.
_NON_ARTICLE_RE = re.compile(
    r"/(?:video|videos|live|photos|Photos)(?:/|$)",
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


def _is_article_url(url):
    """Accept same-site /<Section>/<...>/<slug> URLs, reject video/photo surfaces."""
    if not url:
        return False
    parsed = urlparse(url)
    if (parsed.netloc or "").lower() not in _ALLOWED_HOSTS:
        return False
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return False
    return not _NON_ARTICLE_RE.search(parsed.path)


class ABCNewsScraper(BaseScraper):
    """ABC News adapter driven by the xmlLatestStories news sitemap."""

    BASE_URL = _BASE_URL
    FEED_URL = _FEED_URL
    SOURCE_LABEL = "abcnews.com"
    MAX_ARTICLES_PER_QUERY = 25

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = self.BASE_URL
        self.start_date = start_date
        self._current_keyword = ""
        self.headers = {"Accept-Language": "en-US,en;q=0.9"}

    # ------------------------------------------------------------------
    # Feed parsing
    # ------------------------------------------------------------------
    def _parse_feed(self, response_text):
        """Return [(loc, title, publish_date)] from the news sitemap urlset."""
        if not response_text:
            return []
        head = response_text.lstrip()[:64].lower()
        if not head.startswith("<?xml") and "<urlset" not in head:
            return []
        try:
            root = ET.fromstring(response_text)
        except ET.ParseError as e:
            logging.error("ABC News sitemap parse error: %s", e)
            return []
        if root.tag != f"{{{_SM_NS}}}urlset":
            return []

        entries = []
        for url in root.findall("sm:url", _NSMAP):
            loc = (url.findtext("sm:loc", "", _NSMAP) or "").strip()
            if not loc or not _is_article_url(loc):
                continue
            title = ""
            raw_date = ""
            news = url.find("news:news", _NSMAP)
            if news is not None:
                title = (news.findtext("news:title", "", _NSMAP) or "").strip()
                raw_date = (
                    news.findtext("news:publication_date", "", _NSMAP) or ""
                ).strip()
            if not raw_date:
                raw_date = (url.findtext("sm:lastmod", "", _NSMAP) or "").strip()
            entries.append((loc, title, self.parse_date(raw_date) if raw_date else None))
        return entries

    async def _fetch_feed(self):
        text = await self.fetch(self.FEED_URL, headers=self.headers, timeout=30)
        return self._parse_feed(text)

    def _select(self, entries, tokens):
        """Filter feed entries by keyword tokens and the start_date cutoff."""
        links = []
        seen = set()
        for loc, title, publish_date in entries:
            if self.start_date and publish_date and publish_date < self.start_date:
                continue
            if tokens and not _matches_all_tokens(_normalize(f"{title} {loc}"), tokens):
                continue
            if loc in seen:
                continue
            links.append(loc)
            seen.add(loc)
            if len(links) >= self.MAX_ARTICLES_PER_QUERY:
                break
        return links or None

    # ------------------------------------------------------------------
    # Search path
    # ------------------------------------------------------------------
    async def build_search_url(self, keyword, page):
        self._current_keyword = keyword or ""
        if page != 1:
            return None
        return await self._fetch_feed()

    def parse_article_links(self, response_text_or_entries):
        if not response_text_or_entries:
            return None
        entries = (
            self._parse_feed(response_text_or_entries)
            if isinstance(response_text_or_entries, str)
            else response_text_or_entries
        )
        return self._select(entries, _keyword_tokens(self._current_keyword))

    # ------------------------------------------------------------------
    # Latest path
    # ------------------------------------------------------------------
    async def build_latest_url(self, page):
        if page != 1:
            return None
        return await self._fetch_feed()

    def parse_latest_article_links(self, response_text_or_entries):
        if not response_text_or_entries:
            return None
        entries = (
            self._parse_feed(response_text_or_entries)
            if isinstance(response_text_or_entries, str)
            else response_text_or_entries
        )
        return self._select(entries, [])

    # ------------------------------------------------------------------
    # Article extraction
    # ------------------------------------------------------------------
    async def get_article(self, link, keyword):
        if not _is_article_url(link):
            logging.debug("ABC News rejecting non-article URL: %s", link)
            return

        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("ABC News no response for %s", link)
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
        """The JSON-LD NewsArticle node, or None. ABC also emits WebSite/WebPage."""
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
                    if not isinstance(candidate, dict):
                        continue
                    types = candidate.get("@type") or ""
                    types = types if isinstance(types, list) else [types]
                    if any("NewsArticle" in str(t) or "Article" == str(t) for t in types):
                        return candidate
        return None

    @staticmethod
    def _extract_title(soup, node):
        if node:
            headline = node.get("headline")
            if headline:
                return str(headline).strip()
        meta = soup.find("meta", {"property": "og:title"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        if soup.h1:
            return soup.h1.get_text(strip=True)
        return ""

    def _extract_date(self, soup, node):
        if node:
            for key in ("datePublished", "dateCreated", "dateModified"):
                raw = node.get(key)
                if raw:
                    parsed = self.parse_date(str(raw))
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
            candidates = author if isinstance(author, list) else [author]
            names = []
            for entry in candidates:
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
        if node:
            section = node.get("articleSection")
            if section:
                if isinstance(section, list):
                    section = section[0] if section else ""
                if section:
                    return str(section).strip()
        parts = [p for p in urlparse(link).path.split("/") if p]
        return parts[0] if parts else "news"

    @staticmethod
    def _extract_content(soup):
        body = soup.select_one('div[data-testid="prism-article-body"]')
        if body is None:
            body = soup.select_one("article")
        if body is None:
            return ""
        for tag in list(body.find_all(["script", "style", "iframe", "noscript", "figure"])):
            tag.extract()
        paragraphs = [
            text
            for p in body.find_all("p")
            if len(text := p.get_text(" ", strip=True)) >= 30
        ]
        content = " ".join(paragraphs).strip()
        return content or body.get_text(" ", strip=True)
