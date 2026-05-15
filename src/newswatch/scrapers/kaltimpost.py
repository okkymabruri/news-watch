"""
Kaltim Post (Borneo24) scraper — uses WordPress search with HTML parsing.

https://borneo24.com/?s={keyword}
Article pattern: /{slug}
"""

import json
import logging
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class KaltimPostScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://borneo24.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        # Article URLs are like /{category}/{slug}
        self._skip_paths = [
            "/profile/", "/page/", "/category/", "/tag/", "/author/",
        ]

    async def build_search_url(self, keyword, page):
        params = {"s": keyword}
        if page > 1:
            params["paged"] = page
        url = f"{self.base_url}/?{urlencode(params)}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")

        # Find all links that look like articles (contain dates or category patterns)
        links = set()
        for a in soup.select("a[href]"):
            href = a["href"]
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            # Must be on borneo24.com and not a navigation/admin link
            if full_url.startswith(self.base_url):
                path = full_url.replace(self.base_url, "").strip("/")
                # Skip non-article paths
                if any(skip in full_url for skip in self._skip_paths):
                    continue
                # Must have a meaningful path (not just domain)
                if path and "/" in path:
                    text = a.get_text(strip=True)
                    if text:  # Has visible text = likely an article link
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
        if not title or title == "404":
            return

        # Content — use post-content
        content_div = soup.select_one(".post-content")
        if not content_div:
            content_div = soup.select_one(".entry-content")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        # Remove related/ads/sidebar
        for tag in content_div.find_all(
            ["section", "div"],
            class_=re.compile(
                r"related|popular|most|sidebar|share|social|newsletter|ad|subscribe|embed|author|jetpack|block_",
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

        # Category from URL
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
            "source": "borneo24.com",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        """Extract publish date from meta tags."""
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

        logging.debug("Kaltim Post date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        """Extract author from meta tags."""
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
            if full_url.startswith(self.base_url):
                if any(skip in full_url for skip in self._skip_paths):
                    continue
                path = full_url.replace(self.base_url, "").strip("/")
                if path and "/" in path:
                    text = a.get_text(strip=True)
                    if text:
                        links.add(full_url)
        return links or None
