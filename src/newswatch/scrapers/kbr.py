"""
KBR (kbr.id) scraper — uses Next.js 14+ App Router search endpoint.

https://kbr.id/search?q={keyword}
Article pattern: https://kbr.id/articles/{category}/{slug}
Index page: https://kbr.id/articles/indeks
"""

import json
import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

class KBRScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://kbr.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(r"^https?://kbr\.id/articles/.+")

    async def build_search_url(self, keyword, page):
        params = {"q": keyword}
        if page > 1:
            params["page"] = page
        url = f"{self.base_url}/search?{urlencode(params)}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        links = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = href if href.startswith("http") else f"{self.base_url}{href}"
            if self._article_re.match(full_url):
                links.add(full_url)

        return links if links else None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning("No response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        try:
            # Title: meta og:title -> h1 fallback
            meta_title = soup.find("meta", {"property": "og:title"})
            title = meta_title.get("content", "").strip() if meta_title else ""
            if not title:
                h1 = soup.select_one("h1")
                title = h1.get_text(strip=True) if h1 else ""
            if not title:
                return

            # Content extraction with fallback selectors
            content_div = (
                soup.select_one(".article-content")
                or soup.select_one(".post-content")
                or soup.select_one(".entry-content")
                or soup.select_one("article")
            )
            if not content_div:
                return

            # Remove script/style/iframe
            for tag in content_div.find_all(["script", "style", "iframe"]):
                tag.extract()

            # Remove related/popular/sidebar/ad elements via regex class matching
            for tag in content_div.find_all(
                ["div", "section", "aside"],
                class_=re.compile(r"related|popular|sidebar|ad|recommend|trending|most-read|share|social|newsletter|subscribe|embed|lightbox|promo|widget", re.IGNORECASE)
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

            # Author extraction
            author = self._extract_author(soup)

            # Category from URL path segment after /articles/
            path = link.replace(self.base_url, "").strip("/")
            parts = path.split("/")
            category = parts[1] if len(parts) > 1 else "Unknown"

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "kbr.id",
                "link": link,
            }
            await self.queue_.put(item)

        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)

    def _extract_date(self, soup, link):
        """Extract publish date from meta tags, JSON-LD, or time element."""
        # Try meta article:published_time
        date_meta = soup.find("meta", {"property": "article:published_time"})
        if date_meta and date_meta.get("content"):
            parsed = self.parse_date(date_meta["content"])
            if parsed:
                return parsed

        # Try JSON-LD datePublished
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
        time_elem = soup.find("time")
        if time_elem:
            datetime_attr = time_elem.get("datetime", "")
            if datetime_attr:
                parsed = self.parse_date(datetime_attr)
                if parsed:
                    return parsed
            time_text = time_elem.get_text(strip=True)
            if time_text:
                parsed = self.parse_date(time_text)
                if parsed:
                    return parsed

        logging.debug("KBR date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        """Extract author from meta tags or JSON-LD."""
        # Try meta name="author"
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta and author_meta.get("content"):
            return author_meta["content"].strip()

        # Try meta property="article:author"
        author_meta2 = soup.find("meta", {"property": "article:author"})
        if author_meta2 and author_meta2.get("content"):
            return author_meta2["content"].strip()

        # Try JSON-LD author
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    author_data = data.get("author", "")
                    if isinstance(author_data, dict):
                        name = author_data.get("name", "")
                        if name:
                            return name.strip()
                    elif isinstance(author_data, list) and author_data:
                        name = author_data[0].get("name", "")
                        if name:
                            return name.strip()
                    elif isinstance(author_data, str) and author_data:
                        return author_data.strip()
                except (json.JSONDecodeError, AttributeError, IndexError):
                    continue

        return "Unknown"

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(f"{self.base_url}/articles/indeks")
        return await self.fetch(f"{self.base_url}/articles/indeks?page={page}")

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        links = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = href if href.startswith("http") else f"{self.base_url}{href}"
            if self._article_re.match(full_url):
                links.add(full_url)

        return links if links else None
