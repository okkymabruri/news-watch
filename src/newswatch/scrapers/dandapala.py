"""Dandapala latest-only homepage scraper."""

import json
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_BASE_URL = "https://dandapala.com"
_ARTICLE_RE = re.compile(
    r"^https?://dandapala\.com/article/detail/[a-z0-9][a-z0-9-]*$",
    re.IGNORECASE,
)
_VISIBLE_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b")
_NOISE_CLASS_RE = re.compile(
    r"related|share|social|advert|(^|[-_ ])ad([-_ ]|$)|banner|newsletter|"
    r"sidebar|comment|breadcrumb|pagination",
    re.IGNORECASE,
)


class DandapalaScraper(BaseScraper):
    """Collect Dandapala homepage headlines; search is unsupported."""

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
        }

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return self._collect_links(response_text)

    async def build_latest_url(self, page):
        if page != 1:
            return None
        return await self.fetch(self.base_url, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        return self._collect_links(response_text)

    @staticmethod
    def _collect_links(response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for anchor in soup.select('h3 a[href*="/article/detail/"]'):
            href = anchor.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE_URL, href)
            if _ARTICLE_RE.match(full):
                links.add(full)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("Dandapala empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")
        title = self._extract_title(soup)
        publish_date = self._extract_date(soup)
        content = self._extract_content(soup)
        if not title or not publish_date or not content:
            logging.warning("Dandapala incomplete article: %s", link)
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        await self.queue_.put({
            "title": title,
            "publish_date": publish_date,
            "author": self._extract_author(soup),
            "content": content,
            "keyword": keyword,
            "category": self._extract_category(soup),
            "source": "dandapala.com",
            "link": link,
        })

    @staticmethod
    def _extract_title(soup):
        meta = soup.select_one('meta[property="og:title"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        heading = soup.select_one("h1")
        return heading.get_text(" ", strip=True) if heading else ""

    def _extract_date(self, soup):
        for selector in (
            'meta[property="article:published_time"]',
            'meta[name="publication_date"]',
            'meta[itemprop="datePublished"]',
        ):
            meta = soup.select_one(selector)
            if meta and meta.get("content"):
                parsed = self.parse_date(meta["content"])
                if parsed:
                    return parsed
        for data in self._json_ld_objects(soup):
            raw = data.get("datePublished") or data.get("dateCreated")
            if raw:
                parsed = self.parse_date(str(raw))
                if parsed:
                    return parsed
        match = _VISIBLE_DATE_RE.search(soup.get_text(" ", strip=True))
        return self.parse_date(match.group(0)) if match else None

    @classmethod
    def _extract_author(cls, soup):
        meta = soup.select_one('meta[name="author"], meta[property="article:author"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        for data in cls._json_ld_objects(soup):
            author = data.get("author")
            if isinstance(author, dict) and author.get("name"):
                return str(author["name"]).strip()
            if isinstance(author, list):
                for entry in author:
                    if isinstance(entry, dict) and entry.get("name"):
                        return str(entry["name"]).strip()
        return "Unknown"

    @classmethod
    def _extract_category(cls, soup):
        meta = soup.select_one('meta[property="article:section"], meta[name="category"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        for data in cls._json_ld_objects(soup):
            section = data.get("articleSection")
            if isinstance(section, list) and section:
                return str(section[0]).strip()
            if section:
                return str(section).strip()
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        body = soup.select_one("#article-content") or soup.select_one("article") or soup.select_one("main")
        if not body:
            return ""
        for tag in body.find_all(
            ["script", "style", "iframe", "aside", "nav", "form", "ins"]
        ):
            tag.decompose()
        for tag in body.find_all(True, {"class": _NOISE_CLASS_RE}):
            tag.decompose()
        for tag in body.find_all("p", class_="mt-2"):
            tag.decompose()
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in body.find_all("p")
            if not paragraph.find("p") and paragraph.get_text(" ", strip=True)
        ]
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
