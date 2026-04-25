"""
Mongabay Indonesia scraper — uses WordPress REST API for search.

/wp-json/wp/v2/posts?search={keyword} returns query-specific posts
with keyword in title or content. Nonsense returns empty array.
"""

import json
import logging

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class MongabayScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://mongabay.co.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 5
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    async def build_search_url(self, keyword, page):
        url = f"{self.base_url}/wp-json/wp/v2/posts?search={keyword}&per_page=20&page={page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        try:
            data = json.loads(response_text)
            if not isinstance(data, list):
                return None
            items = []
            for item in data:
                link = item.get("link", "")
                title = item.get("title", {}).get("rendered", "")
                content = item.get("content", {}).get("rendered", "")
                if link and title:
                    items.append({"link": link, "title": title, "content": content, "date": item.get("date", "")})
            return items if items else None
        except Exception:
            return None

    async def fetch_search_results(self, keyword):
        page = 1
        found_articles = False

        while self.continue_scraping and page <= self.max_pages:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break

            items = self.parse_article_links(response_text)
            if not items:
                break

            found_articles = True
            for item in items:
                await self._process_api_item(item, keyword)

            if len(items) < 20:
                break
            page += 1

        if not found_articles:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def _process_api_item(self, item, keyword):
        link = item["link"]
        title = BeautifulSoup(item["title"], "html.parser").get_text(strip=True)
        content = BeautifulSoup(item["content"], "html.parser").get_text(" ", strip=True)
        publish_date_str = item.get("date", "")
        publish_date = self.parse_date(publish_date_str)

        if not publish_date:
            logging.debug("Mongabay date parse failed | url: %s | date: %r", link, publish_date_str[:50])
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        path = link.replace(self.base_url, "").strip("/")
        parts = path.split("/")
        category = parts[0] if parts else "Unknown"

        article = {
            "title": title,
            "publish_date": publish_date,
            "author": "Unknown",
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "mongabay.co.id",
            "link": link,
        }
        await self.queue_.put(article)

    # Satisfy abstract methods (not used — articles from API JSON)
    async def get_article(self, link, keyword):
        pass
