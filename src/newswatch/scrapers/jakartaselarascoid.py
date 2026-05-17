"""
Jakarta Selaras scraper — custom CMS with RSS/sitemap discovery.

https://jakarta.selaras.co.id/detail/{id}/{slug}
Search mode: RSS/sitemap keyword filtering (native /?s= mirrors homepage).
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

class JakartaSelarasScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://jakarta.selaras.co.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(
            r"^https?://jakarta\.selaras\.co\.id/detail/\d+/[a-z0-9-]+/?$"
        )
        self._skip_paths = [
            "/read/", "/kanal/", "/rss", "/sitemap", "/tema2023/",
            "/ic/", "/ads/", "/cdn-cgi/",
        ]

    async def build_search_url(self, keyword, page):
        # Native search not validated; use RSS for discovery
        return await self.fetch(f"{self.base_url}/rss")

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        # Parse RSS and filter by keyword in title/link
        links = set()
        try:
            root = ET.fromstring(response_text)
            for item in root.iter("item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                if self._article_re.match(link) and self._match_keyword(title, self.current_keyword):
                    links.add(link)
        except ET.ParseError:
            soup = BeautifulSoup(response_text, "html.parser")
            for a in soup.select("a[href]"):
                href = a["href"]
                full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
                if self._article_re.match(full_url) and not any(skip in full_url for skip in self._skip_paths):
                    title = a.get_text(" ", strip=True)
                    if self._match_keyword(title, self.current_keyword):
                        links.add(full_url)
        return links or None

    def _match_keyword(self, text, keyword):
        if not text or not keyword:
            return True
        return keyword.lower() in text.lower()

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning("No response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        # Title from JSON-LD then h1
        title = None
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        headline = data.get("headline", "")
                        if headline:
                            title = headline.strip()
                            break
                except (json.JSONDecodeError, AttributeError):
                    continue
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        if not title:
            return

        # Date from JSON-LD
        publish_date = None
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        date_str = data.get("datePublished", "")
                        if date_str:
                            publish_date = self.parse_date(date_str)
                            if publish_date:
                                break
                except (json.JSONDecodeError, AttributeError):
                    continue
        if not publish_date:
            logging.debug("Selaras date parse failed | url: %s", link)
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        # Content
        content_div = soup.select_one(".post_content")
        if not content_div:
            content_div = soup.select_one(".endmark")
        if not content_div:
            content_div = soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        # Author from JSON-LD
        author = "Unknown"
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        author_data = data.get("author", {})
                        if isinstance(author_data, dict):
                            name = author_data.get("name", "")
                            if name:
                                author = name
                                break
                        elif isinstance(author_data, str):
                            author = author_data
                            break
                except (json.JSONDecodeError, AttributeError):
                    continue

        # Category from visible metadata or URL
        category = "Unknown"
        section_meta = soup.select_one('meta[property="article:section"]')
        if section_meta and section_meta.get("content"):
            category = section_meta["content"].strip()

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "jakarta.selaras.co.id",
            "link": link,
        }
        await self.queue_.put(item)

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(f"{self.base_url}/rss")
        return None

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        links = set()
        try:
            root = ET.fromstring(response_text)
            for item in root.iter("item"):
                link = item.findtext("link", "")
                if self._article_re.match(link):
                    links.add(link)
        except ET.ParseError:
            soup = BeautifulSoup(response_text, "html.parser")
            for a in soup.select("a[href]"):
                href = a["href"]
                full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
                if self._article_re.match(full_url) and not any(skip in full_url for skip in self._skip_paths):
                    links.add(full_url)
        return links or None
