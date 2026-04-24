"""
SurabayaPagi scraper — uses tag page with keyword filtering.

https://surabayapagi.com/tag/{keyword}
"""

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class SurabayaPagiScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://surabayapagi.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(r"https?://surabayapagi\.com/news-\d+-")

    async def build_search_url(self, keyword, page):
        if page == 1:
            url = f"{self.base_url}/tag/{quote(keyword, safe='')}"
        else:
            url = f"{self.base_url}/tag/{quote(keyword, safe='')}?page={page}"
        return await self.fetch(url, timeout=30)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()

        for h in soup.select("h2 a[href], h3 a[href]"):
            href = h.get("href", "")
            if self._article_re.match(href):
                links.add(href if href.startswith("http") else f"{self.base_url}{href}")

        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title_elem = soup.select_one("h1") or soup.select_one('meta[property="og:title"]')
        title = (title_elem.get("content", "") or title_elem.get_text(strip="")) if title_elem else ""
        if not title:
            return

        author_elem = soup.select_one('meta[name="author"]') or soup.select_one(".author")
        author = (author_elem.get("content", "") or author_elem.get_text(strip="")) if author_elem else "Unknown"

        date_elem = soup.select_one('meta[property="article:published_time"]')
        publish_date_str = ""
        if date_elem:
            publish_date_str = date_elem.get("content", "")

        content_div = soup.select_one('div[itemprop="articleBody"]') or soup.select_one("div.article-content") or soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        publish_date = self.parse_date(publish_date_str)
        if not publish_date:
            logging.debug("SurabayaPagi date parse failed | url: %s | date: %r", link, publish_date_str[:50])
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

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
            "source": "surabayapagi",
            "link": link,
        }
        await self.queue_.put(item)
