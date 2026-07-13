"""
Al Jazeera scraper — latest-only via RSS feed.

The public GraphQL search requires a per-request reCAPTCHA token, so search remains unsupported.
Uses RSS feed for latest: https://www.aljazeera.com/xml/rss/all.xml
Article pattern: /{year}/{month}/{day}/{slug}
"""

import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class AlJazeeraScraper(BaseScraper):
    def __init__(self, keywords, concurrency=3, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.aljazeera.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_latest_pages = 1
        self._article_re = re.compile(
            r"^https?://(?:www\.)?aljazeera\.com/[^/]+/\d{4}/\d{1,2}/\d{1,2}/.+$"
        )
        self._skip_paths = frozenset(
            ["/liveblog/", "/video/", "/podcast/", "/gallery/", "/program/", "/where/"]
        )

    async def build_search_url(self, keyword, page):
        # /graphql SearchQuery requires a per-request reCAPTCHA token.
        logging.info("Al Jazeera search mode is reCAPTCHA-gated; use latest mode.")
        self.continue_scraping = False
        return None

    def parse_article_links(self, response_text):
        # Not used in latest-only mode
        return None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning("No response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        # Title
        title_el = soup.select_one('meta[property="og:title"]')
        title = (title_el.get("content", "").strip()) if title_el else ""
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        if not title:
            return

        # Content
        content_div = soup.select_one("div.article-body") or soup.select_one("div.wysiwyg")
        if not content_div:
            content_div = soup.select_one("div[class*='article-body']")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        for tag in content_div.find_all(
            ["section", "div"],
            class_=re.compile(r"related|most|popular|share|social|newsletter|ad|subscribe|embed|more", re.IGNORECASE),
        ):
            tag.extract()

        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        # Date extraction
        publish_date = self._extract_date(soup, link)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        # Author
        author = self._extract_author(soup)

        # Category from URL
        path = link.replace(self.base_url, "").strip("/")
        parts = path.split("/")
        category = parts[1] if len(parts) > 1 else "News"

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "aljazeera.com",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        # Try JSON-LD first
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    date_str = data.get("datePublished", "")
                    if date_str:
                        parsed = self.parse_date(date_str)
                        if parsed:
                            return parsed
                except (json.JSONDecodeError, AttributeError):
                    continue

        # Try meta article:published_time
        date_meta = soup.select_one('meta[property="article:published_time"]')
        if date_meta and date_meta.get("content"):
            parsed = self.parse_date(date_meta["content"])
            if parsed:
                return parsed

        # Try time element
        time_el = soup.select_one("time[datetime]")
        if time_el:
            parsed = self.parse_date(time_el["datetime"])
            if parsed:
                return parsed

        # Try parsing from URL path /YYYY/MM/DD/...
        match = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", link)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        logging.debug("Al Jazeera date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        author_meta = soup.select_one('meta[name="author"]')
        if author_meta and author_meta.get("content"):
            return author_meta["content"].strip()

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    author_data = data.get("author", {})
                    if isinstance(author_data, dict):
                        name = author_data.get("name", "")
                        if name:
                            return name
                    elif isinstance(author_data, list) and author_data:
                        names = [a.get("name", "") for a in author_data if a.get("name")]
                        if names:
                            return ", ".join(names)
                except (json.JSONDecodeError, AttributeError, IndexError):
                    continue

        return "Unknown"

    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(f"{self.base_url}/xml/rss/all.xml", timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "xml")
        links = set()
        for item in soup.find_all("item"):
            link_el = item.find("link")
            if link_el:
                link = link_el.get_text(strip=True)
                if self._article_re.match(link):
                    if not any(p in link for p in self._skip_paths):
                        links.add(link)
        return links or None
