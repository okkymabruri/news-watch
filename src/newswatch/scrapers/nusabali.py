"""
NusaBali scraper — Bali regional newspaper.

Verified endpoints (2026-07-12):
    search:  https://www.nusabali.com/search?keyword={quoted_keyword}&page={page}
    latest:  https://www.nusabali.com/
    article: https://www.nusabali.com/berita/{numeric-id}/{slug}

Article extraction sources (verified 2026-07-12 against
https://www.nusabali.com/berita/225365/pria-mabuk-di-desa-keramas-diamankan-polisi):
- title:    meta[property="og:title"]; fallback span[itemprop="headline"] inside h1
- date:     span.month.pull-left[itemprop="datePublished"] inside .entry-box-header
            (e.g. "12 Jul 2026 19:37:24")
- author:   span[itemprop="author"] inside the byline below .entry-content
            (preceded by "Penulis : ")
- category: .breadcrumb span.article-category[itemprop="articleSection"];
            falls back to "Unknown"
- body:     <p> children of div.entry-content[itemprop="articleBody"];
            strips related/nav/share/sidebar/terkait blocks before extraction.
"""

import logging
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_BASE_URL = "https://www.nusabali.com"
_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?nusabali\.com/berita/\d+/[a-z0-9][a-z0-9-]*$",
    re.IGNORECASE,
)
_NAV_CLASS_RE = re.compile(
    r"related|popular|most|sidebar|share|social|newsletter|ad|subscribe|"
    r"embed|comment|promoted|terkait|baca-juga|tag-box|breadcrumb",
    re.IGNORECASE,
)


class NusaBaliScraper(BaseScraper):
    """NusaBali scraper with /search?keyword= search and homepage latest."""

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
        }

    async def build_search_url(self, keyword, page):
        if page < 1:
            page = 1
        quoted = quote(keyword, safe="")
        url = f"{_BASE_URL}/search?keyword={quoted}&page={page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        return self._collect_article_links(response_text)

    async def build_latest_url(self, page):
        if page != 1:
            return None
        return await self.fetch(self.base_url, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        return self._collect_article_links(response_text)

    @staticmethod
    def _collect_article_links(response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE_URL, href)
            if _ARTICLE_RE.match(full):
                links.add(full)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("NusaBali empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            logging.warning("NusaBali missing title: %s", link)
            return

        publish_date = self._extract_date(soup)
        if not publish_date:
            logging.warning("NusaBali missing date: %s", link)
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        content = self._extract_content(soup)
        if not content:
            logging.warning("NusaBali empty content: %s", link)
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
            "source": "nusabali.com",
            "link": link,
        })

    @staticmethod
    def _extract_title(soup):
        meta = soup.select_one('meta[property="og:title"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        h1 = soup.select_one("h1 span[itemprop='headline']") or soup.select_one("h1")
        if h1:
            return h1.get_text(strip=True)
        return ""

    def _extract_date(self, soup):
        span = soup.select_one(
            ".entry-box-header span.month.pull-left[itemprop='datePublished']"
        )
        if not span:
            span = soup.select_one("span[itemprop='datePublished']")
        if not span:
            return None
        raw = span.get_text(" ", strip=True)
        return self.parse_date(raw)

    @staticmethod
    def _extract_author(soup):
        author = soup.select_one('.entry-content + span[itemprop="author"], span[itemprop="author"]')
        if not author:
            return "Unknown"
        text = author.get_text(" ", strip=True)
        if not text:
            return "Unknown"
        return text

    @staticmethod
    def _extract_category(soup):
        crumb = soup.select_one(
            ".breadcrumb span.article-category[itemprop='articleSection']"
        )
        if not crumb:
            crumb = soup.select_one("span[itemprop='articleSection']")
        if crumb:
            text = crumb.get_text(strip=True)
            if text:
                return text
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        body = soup.select_one("div.entry-content[itemprop='articleBody']")
        if not body:
            return ""
        # Strip nav/share/sidebar blocks before collecting paragraphs.
        for tag in body.find_all(
            [
                "aside",
                "nav",
                "script",
                "style",
                "ins",
                "iframe",
                "form",
            ]
        ):
            tag.decompose()
        for tag in body.find_all(True, {"class": _NAV_CLASS_RE}):
            tag.decompose()

        paragraphs = []
        for p in body.find_all("p"):
            text = p.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        if not paragraphs:
            return ""
        return re.sub(r"\s+", " ", " ".join(paragraphs)).strip()
