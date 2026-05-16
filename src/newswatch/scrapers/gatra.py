"""
Gatra scraper — uses WordPress search with title-based keyword filtering.

https://www.gatra.net/?s={keyword}
Article pattern: /news-NNNNNN-{category}-{slug}.html

NOTE: Gatra's WordPress search returns all articles regardless of query.
Articles are filtered by keyword presence in the visible title text.
"""

import logging                           # logging first
import json
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class GatraScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.gatra.net"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(
            r"^https?://www\.gatra\.net/news-\d+-"
        )

    async def build_search_url(self, keyword, page):
        params = {"s": keyword}
        if page > 1:
            params["paged"] = page
        url = f"{self.base_url}/?{urlencode(params)}"
        self._current_keyword = keyword.lower()  # store for parse_article_links
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")

        # Gatra search returns all articles regardless of query;
        # filter strictly by keyword presence in the visible title text.
        links = set()
        kw = self._current_keyword  # set by build_search_url with active keyword
        for a in soup.select("a[href]"):
            href = a["href"]
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                title = a.get_text(strip=True)
                if title and kw and kw in title.lower():
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

        # Content — use td-post-content (Newspaper theme like Bali Post)
        content_div = soup.select_one(".td-post-content")
        if not content_div:
            content_div = soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        # Remove related/ads/sidebar sections
        for tag in content_div.find_all(
            ["section", "div", "footer"],
            class_=re.compile(
                r"related|popular|most|sidebar|share|social|newsletter|ad|subscribe|embed|block_related|td-related",
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

        # Category from URL path (e.g., news-603341-hukum-slug.html -> hukum)
        path = link.replace(self.base_url, "").strip("/")
        parts = path.replace(".html", "").split("-")
        # Skip the "news" and ID number, take the category slug
        if len(parts) > 2:
            category = parts[2] if len(parts) > 2 else "Unknown"
        else:
            category = "Unknown"

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "gatra.net",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        """Extract publish date from meta tags or HTML."""
        # Try meta article:published_time
        date_meta = soup.select_one('meta[property="article:published_time"]')
        if date_meta and date_meta.get("content"):
            parsed = self.parse_date(date_meta["content"])
            if parsed:
                return parsed

        # Try .entry-date (Newspaper theme)
        date_el = soup.select_one(".entry-date")
        if date_el:
            parsed = self.parse_date(date_el.get_text(strip=True))
            if parsed:
                return parsed

        # Try time element
        time_el = soup.select_one("time")
        if time_el:
            parsed = self.parse_date(time_el.get_text(strip=True))
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

        logging.debug("Gatra date parse failed | url: %s", link)
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
