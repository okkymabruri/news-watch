"""Banten News WordPress search and homepage scraper."""

import json
import logging
import re
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_BASE_URL = "https://www.bantennews.co.id"
_EXCLUDED_PATHS = {
    "about",
    "category",
    "contact",
    "feed",
    "page",
    "privacy-policy",
    "redaksi",
    "tag",
}
_NOISE_CLASS_RE = re.compile(
    r"related|share|social|advert|(^|[-_ ])ad([-_ ]|$)|banner|newsletter|"
    r"sidebar|comment|author-box|post-tags|baca-juga",
    re.IGNORECASE,
)


class BantenNewsScraper(BaseScraper):
    """Collect Banten News search results and homepage headlines."""

    def __init__(self, keywords, concurrency=3, start_date=None, queue_=None):
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
        if page < 1:
            page = 1
        quoted = quote(keyword, safe="")
        path = f"/?s={quoted}" if page == 1 else f"/page/{page}/?s={quoted}"
        return await self.fetch(
            f"{_BASE_URL}{path}", headers=self.headers, timeout=30
        )

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
        for anchor in soup.select(".entry-title.td-module-title a[href]"):
            href = anchor.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE_URL, href)
            parsed = urlparse(full)
            parts = [part for part in parsed.path.split("/") if part]
            if (
                parsed.hostname in {"bantennews.co.id", "www.bantennews.co.id"}
                and len(parts) == 1
                and parts[0].lower() not in _EXCLUDED_PATHS
            ):
                links.add(full)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("Banten News empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")
        title = self._extract_title(soup)
        publish_date = self._extract_date(soup)
        content = self._extract_content(soup)
        if not title or not publish_date or not content:
            logging.warning("Banten News incomplete article: %s", link)
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
            "source": "bantennews.co.id",
            "link": link,
        })

    @staticmethod
    def _extract_title(soup):
        heading = soup.select_one("h1.entry-title")
        if heading:
            title = heading.get_text(" ", strip=True)
            if title:
                return title
        meta = soup.select_one('meta[property="og:title"]')
        return meta.get("content", "").strip() if meta else ""

    def _extract_date(self, soup):
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            parsed = self.parse_date(meta["content"])
            if parsed:
                return parsed
        time = soup.select_one("time.entry-date[datetime]")
        if time:
            return self.parse_date(time["datetime"])
        return None

    @staticmethod
    def _extract_author(soup):
        meta = soup.select_one('meta[name="author"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        visible = soup.select_one(".td-post-author-name a, .author-name, .entry-author a")
        if visible:
            author = visible.get_text(" ", strip=True)
            if author:
                return author
        return "Unknown"

    @classmethod
    def _extract_category(cls, soup):
        for data in cls._json_ld_objects(soup):
            section = data.get("articleSection")
            if isinstance(section, list) and section:
                return str(section[0]).strip()
            if section:
                return str(section).strip()
        for selector in (
            'meta[property="article:section"]',
            'meta[name="category"]',
        ):
            meta = soup.select_one(selector)
            if meta and meta.get("content"):
                return meta["content"].strip()
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        body = soup.select_one("div.td-post-content")
        if not body:
            return ""
        for tag in body.find_all(
            ["script", "style", "iframe", "aside", "nav", "form", "ins"]
        ):
            tag.decompose()
        for tag in body.find_all(True, {"class": _NOISE_CLASS_RE}):
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
