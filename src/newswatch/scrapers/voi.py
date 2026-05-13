"""
VOI.id scraper — uses search endpoint with HTML parsing.

https://voi.id/en/artikel/cari?q={keyword}
"""

import json
import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class VOIScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://voi.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10

    async def build_search_url(self, keyword, page):
        params = {"q": keyword}
        if page > 1:
            params["page"] = page
        url = f"{self.base_url}/en/artikel/cari?{urlencode(params)}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")

        # No-result marker check
        no_result = soup.find(string=re.compile(r"Found 0 articles", re.IGNORECASE))
        if no_result:
            return None

        links = set()
        for title_elem in soup.select(".section-item-title a"):
            href = title_elem.get("href", "")
            if href:
                links.add(href)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning("No response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        # Title from og:title
        title_el = soup.select_one('meta[property="og:title"]')
        title = (title_el.get("content", "").strip()) if title_el else ""
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        if not title:
            return

        # Content — prefer specific post-body selector, remove sidebar/related
        content_div = soup.select_one("div.single-post-content") or soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        # Remove sidebar/related sections that pollute content
        for tag in content_div.find_all(["section", "div"], class_=re.compile(r"related|popular|most|sidebar|see-also", re.IGNORECASE)):
            tag.extract()

        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        # Date extraction — try JSON-LD first, then meta, then text
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
        category = parts[0] if parts else "Unknown"

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "voi.id",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        """Extract publish date from JSON-LD or meta tags."""
        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    date_str = data.get("datePublished", "")
                    if date_str:
                        # Handle format like "2026-05-13WIB18:45:00+07:00"
                        date_str = date_str.replace("WIB", " ").strip()
                        parsed = self.parse_date(date_str)
                        if parsed:
                            return parsed
                except (json.JSONDecodeError, AttributeError):
                    continue

        # Try meta tags
        date_meta = soup.select_one('meta[property="article:published_time"]')
        if date_meta and date_meta.get("content"):
            parsed = self.parse_date(date_meta["content"])
            if parsed:
                return parsed

        # Try text date element
        date_el = soup.select_one(".single-post-date time")
        if date_el:
            parsed = self.parse_date(date_el.get_text(strip=True))
            if parsed:
                return parsed

        logging.debug("VOI date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        """Extract author from JSON-LD or HTML elements."""
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

        # Try HTML
        author_el = soup.select_one(".single-post-author a") or soup.select_one('meta[name="author"]')
        if author_el:
            text = author_el.get("content", "") or author_el.get_text(strip=True)
            if text:
                return text

        return "Unknown"

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(f"{self.base_url}/en/artikel/indeks")
        return await self.fetch(f"{self.base_url}/en/artikel/indeks?page={page}")

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for title_elem in soup.select(".section-item-title a"):
            href = title_elem.get("href", "")
            if href and "/en/" in href and "/artikel/" not in href:
                # Filter to article pages only
                links.add(href)
        return links or None
