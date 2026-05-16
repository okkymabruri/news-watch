"""
Fajar scraper — uses WordPress search with HTML parsing.

https://fajar.co.id/?s={keyword}
Article pattern: /{year}/{month}/{day}/{slug}/
"""

import json
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

class FajarScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://fajar.co.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(
            r"^https?://fajar\.co\.id/\d{4}/\d{2}/\d{2}/.+$"
        )

    async def build_search_url(self, keyword, page):
        if page == 1:
            url = f"{self.base_url}/?s={keyword}"
        else:
            url = f"{self.base_url}/page/{page}/?s={keyword}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")

        links = set()
        for a in soup.select("a[href]"):
            href = a["href"]
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                links.add(full_url)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning("No response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        # Title
        title_el = soup.select_one('meta[property="og:title"]')
        title = title_el.get("content", "").strip() if title_el else ""
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        if not title:
            return

        # Content
        content_div = soup.select_one(".entry-content")
        if not content_div:
            content_div = soup.select_one(".post-content")
        if not content_div:
            content_div = soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        for tag in content_div.find_all(
            ["section", "div", "footer"],
            class_=re.compile(
                r"related|popular|most|sidebar|share|social|newsletter|ad|subscribe|embed|block_related|td-related|author-box|post-tags|comments|wp-block",
                re.IGNORECASE,
            ),
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

        # Category from URL path
        path = link.replace(self.base_url, "").strip("/")
        parts = path.split("/")
        category = parts[0] if len(parts) > 3 else "Unknown"

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "fajar.co.id",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        # Try meta article:published_time
        date_meta = soup.select_one('meta[property="article:published_time"]')
        if date_meta and date_meta.get("content"):
            parsed = self.parse_date(date_meta["content"])
            if parsed:
                return parsed

        # Try JSON-LD
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

        # Try time element
        time_el = soup.select_one("time")
        if time_el:
            parsed = self.parse_date(time_el.get_text(strip=True))
            if parsed:
                return parsed

        logging.debug("Fajar date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        # Try meta author
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
                except (json.JSONDecodeError, AttributeError):
                    continue

        return "Unknown"

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(self.base_url)
        return await self.fetch(f"{self.base_url}/page/{page}/")

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a["href"]
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                links.add(full_url)
        return links or None
