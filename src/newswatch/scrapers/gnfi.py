"""
GNFI (Good News From Indonesia) scraper.

Search:   https://www.goodnewsfromindonesia.id/search?keyword={kw}[&page=N]
Latest:   https://www.goodnewsfromindonesia.id/explore
Articles: https://www.goodnewsfromindonesia.id/YYYY/MM/DD/{slug}

Article extraction sources (verified 2026-07-12):
- title:    meta[property="og:title"]
- date:     JSON-LD "datePublished" (fallback: meta article:published_time)
- author:   meta[name="author"]
- category: div.article-category a
- body:     all <p data-path-to-node="..."> inside div.article-sheet

Only same-site dated article URLs (YYYY/MM/DD/{slug}) are accepted.
"""

import json
import logging
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?goodnewsfromindonesia\.id/\d{4}/\d{2}/\d{2}/[a-z0-9][a-z0-9-]*$",
    re.IGNORECASE,
)
_BASE_URL = "https://www.goodnewsfromindonesia.id"
_MAX_PAGES = 5


class GNFIScraper(BaseScraper):
    """GNFI search + latest via static HTML endpoints."""

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = _BASE_URL
        self.start_date = start_date
        self.continue_scraping = True
        self._current_keyword = ""
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    async def build_search_url(self, keyword, page):
        """Search: ?keyword={quoted}[&page=N]. page 1 omits page=."""
        self._current_keyword = keyword
        encoded = quote(keyword, safe="")
        url = f"{self.base_url}/search?keyword={encoded}"
        if page > 1:
            url += f"&page={page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def _collect_article_links(self, response_text, keyword=""):
        if not response_text:
            return None
        tokens = [token.lower() for token in re.findall(r"\w+", keyword)]
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            full = href if href.startswith("http") else urljoin(self.base_url, href)
            title = a.get("title", "") or a.get_text(" ", strip=True)
            haystack = f"{full} {title}".lower()
            if _ARTICLE_RE.match(full) and all(token in haystack for token in tokens):
                links.add(full)
        return links or None

    def parse_article_links(self, response_text):
        return self._collect_article_links(response_text, self._current_keyword)

    async def build_latest_url(self, page):
        if page != 1:
            return None
        return await self.fetch(f"{self.base_url}/explore", headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        return self._collect_article_links(response_text)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("GNFI empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            return

        publish_date = self._extract_date(soup)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        content = self._extract_content(soup)
        if not content:
            return

        author = self._extract_author(soup)
        category = self._extract_category(soup)

        await self.queue_.put({
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "goodnewsfromindonesia.id",
            "link": link,
        })

    @staticmethod
    def _extract_title(soup):
        el = soup.select_one('meta[property="og:title"]')
        if el and el.get("content"):
            return el["content"].strip()
        h1 = soup.select_one("h1")
        return h1.get_text(strip=True) if h1 else ""

    def _extract_date(self, soup):
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.get_text() or "")
            except (ValueError, TypeError):
                continue
            stamp = self._date_from_jsonld(data)
            if stamp:
                return stamp
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            stamp = self.parse_date(meta["content"])
            if stamp:
                return stamp
        return None

    @staticmethod
    def _date_from_jsonld(node):
        if isinstance(node, dict):
            stamp = node.get("datePublished")
            if isinstance(stamp, str):
                from dateparser import parse as _parse
                parsed = _parse(stamp)
                if parsed:
                    return parsed.replace(tzinfo=None)
            for key in ("@graph", "mainEntity"):
                if key in node:
                    inner = GNFIScraper._date_from_jsonld(node[key])
                    if inner:
                        return inner
        elif isinstance(node, list):
            for item in node:
                inner = GNFIScraper._date_from_jsonld(item)
                if inner:
                    return inner
        return None

    @staticmethod
    def _extract_author(soup):
        meta = soup.select_one('meta[name="author"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.get_text() or "")
            except (ValueError, TypeError):
                continue
            name = GNFIScraper._author_from_jsonld(data)
            if name:
                return name
        return "Unknown"

    @staticmethod
    def _author_from_jsonld(node):
        if isinstance(node, dict):
            author = node.get("author")
            if isinstance(author, dict):
                name = author.get("name")
                if name:
                    return name
            elif isinstance(author, list) and author:
                first = author[0]
                if isinstance(first, dict) and first.get("name"):
                    return first["name"]
                if isinstance(first, str):
                    return first
            for key in ("@graph", "mainEntity"):
                if key in node:
                    inner = GNFIScraper._author_from_jsonld(node[key])
                    if inner:
                        return inner
        elif isinstance(node, list):
            for item in node:
                inner = GNFIScraper._author_from_jsonld(item)
                if inner:
                    return inner
        return None

    @staticmethod
    def _extract_category(soup):
        cat_div = soup.select_one("div.article-category a")
        if cat_div:
            return cat_div.get_text(strip=True) or "Unknown"
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        sheet = soup.select_one("div.article-sheet")
        if not sheet:
            return ""
        for tag in sheet.find_all(["script", "style", "iframe"]):
            tag.extract()
        for tag in sheet.find_all(
            ["section", "div", "aside", "footer"],
            class_=re.compile(
                r"ads|ad-|sponsor|related|popular|share|social|newsletter|"
                r"subscribe|comments|sidebar|embed|promo|tag|topic",
                re.IGNORECASE,
            ),
        ):
            tag.extract()
        paragraphs = sheet.select("p[data-path-to-node]")
        if not paragraphs:
            return ""
        text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
        return re.sub(r"\s+", " ", text).strip()

    async def fetch_search_results(self, keyword):
        page = 1
        found = False
        while self.continue_scraping and page <= _MAX_PAGES:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break
            links = self.parse_article_links(response_text)
            if not links:
                break
            found = True
            await self.process_page(self._filter_links(links), keyword)
            page += 1
        if not found:
            logging.info("No news found on %s for keyword: '%s'", self.base_url, keyword)
