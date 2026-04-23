"""
KBR scraper — uses index page with keyword filtering.

Search is not available; uses index page and filters by keyword in titles.
"""

import logging
from urllib.parse import quote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class KbrScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://kbr.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10

    async def build_search_url(self, keyword, page):
        return f"{self.base_url}/?s={quote(keyword, safe='')}"

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        kw_lower = ""
        for kw in self.keywords:
            if kw.lower() in response_text.lower():
                kw_lower = kw.lower()
                break

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if href.startswith("/articles/indeks/") and len(href) > 30:
                title = a.get_text(strip=True)
                if title and kw_lower and kw_lower in title.lower():
                    full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                    links.add(full_url)

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

        kw_lower = keyword.lower()
        if kw_lower not in title.lower() and kw_lower not in link.lower():
            return

        author_elem = soup.select_one('meta[name="author"]') or soup.select_one(".author")
        author = (author_elem.get("content", "") or author_elem.get_text(strip="")) if author_elem else "Unknown"

        date_elem = soup.select_one('meta[property="article:published_time"]')
        publish_date_str = ""
        if date_elem:
            publish_date_str = date_elem.get("content", "")

        content_div = soup.select_one('div[itemprop="articleBody"]') or soup.select_one(".article-content") or soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        publish_date = self.parse_date(publish_date_str)
        if not publish_date:
            logging.debug("KBR date parse failed | url: %s | date: %r", link, publish_date_str[:50])
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

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
