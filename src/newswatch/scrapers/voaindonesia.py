"""
VOA Indonesia scraper — uses search endpoint with HTML parsing.

https://www.voaindonesia.com/s?k={keyword}
Article pattern: /a/slug/NNNNNNN.html
"""

import json
import logging
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class VOAIndonesiaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.voaindonesia.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(r"^https?://(?:www\.)?voaindonesia\.com/a/.+\.html$")

    async def build_search_url(self, keyword, page):
        params = {"k": keyword}
        if page > 1:
            params["page"] = page
        url = f"{self.base_url}/s?{urlencode(params)}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")

        # No results check
        no_result = soup.find(string=re.compile(r"Hasil Pencarian", re.IGNORECASE))
        if no_result:
            search_results = soup.select_one("#search-results")
            if search_results and not search_results.select("a[href]"):
                return None

        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                # Verify it's an actual article link (not subscribe or other)
                if "/subscribe" not in full_url:
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
        title = (title_el.get("content", "").strip()) if title_el else ""
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        if not title:
            return

        # Content — use specific content selector found in VOA Indonesia articles
        content_div = soup.select_one("div.body-container") or soup.select_one("div.content-floated-wrap")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        for tag in content_div.find_all(["section", "div"], class_=re.compile(r"related|popular|most|sidebar|share|social|newsletter|ad|subscribe|embed|lightbox|advisory|sharing|article-tools|c-mmp", re.IGNORECASE)):
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
        category = parts[0] if parts else "Unknown"

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "voaindonesia.com",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        """Extract publish date from meta tags or JSON-LD."""
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

        # Try meta datePublished
        date_meta2 = soup.select_one('meta[name="datePublished"]')
        if date_meta2 and date_meta2.get("content"):
            parsed = self.parse_date(date_meta2["content"])
            if parsed:
                return parsed

        logging.debug("VOA Indonesia date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        """Extract author from meta tags or HTML."""
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
                    elif isinstance(author_data, list) and author_data:
                        name = author_data[0].get("name", "")
                        if name:
                            return name
                except (json.JSONDecodeError, AttributeError, IndexError):
                    continue

        return "Unknown"

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(self.base_url)
        return await self.fetch(f"{self.base_url}/z")

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url) and "/subscribe" not in full_url:
                links.add(full_url)
        return links or None
