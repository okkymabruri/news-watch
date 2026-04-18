"""
RRI (rri.co.id) scraper — uses the site's /search?q= endpoint.

Plain HTTP works; no Playwright needed.
Pagination via /search?q=...&page=N
"""

import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class RRIScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://rri.co.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }
        self._article_href = re.compile(
            r"^https?://rri\.co\.id/.+/\d+/.+"
        )
        self._seen_links = set()

    async def build_search_url(self, keyword, page):
        query_params = {"q": keyword, "page": page}
        url = f"{self.base_url}/search?{urlencode(query_params)}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        filtered_hrefs = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if self._article_href.match(href) and href not in self._seen_links:
                self._seen_links.add(href)
                filtered_hrefs.add(href)

        if not filtered_hrefs:
            self.continue_scraping = False

        return filtered_hrefs if filtered_hrefs else None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            # Title from og:title meta
            meta_title = soup.find("meta", {"property": "og:title"})
            title = meta_title.get("content", "").split(" - ")[0].strip() if meta_title else ""
            if not title:
                h1 = soup.select_one("h1")
                title = h1.get_text(strip=True) if h1 else ""
            if not title:
                return

            # Date
            date_el = soup.select_one(".date")
            publish_date_str = date_el.get_text(strip=True) if date_el else ""
            publish_date_str = publish_date_str.strip().replace("\n", " ").replace("WIB", "").strip()

            # Content
            content_div = soup.select_one(".post_details_inner") or soup.select_one(".main-content")
            if not content_div:
                return

            paragraphs = [p.get_text(" ", strip=True) for p in content_div.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                content = content_div.get_text(" ", strip=True)
            if not content:
                return

            # Author
            author_el = soup.select_one(".author")
            author = "Unknown"
            if author_el:
                author_text = author_el.get_text(strip=True)
                author_text = author_text.replace("Oleh -", "").replace("Oleh", "").strip().rstrip(",").strip()
                if author_text:
                    author = author_text

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.debug(
                    "RRI date parse failed | url: %s | date: %r",
                    link,
                    publish_date_str[:50],
                )
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            # Category from URL
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
                "source": "rri.co.id",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
