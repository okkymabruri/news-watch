"""
RM.ID scraper — uses search page with title-based keyword filtering.

https://rm.id/?s=KEYWORD
"""

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class RmidScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://rm.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 5
        self._article_re = re.compile(r"https?://rm\.id/baca-berita/")

    async def build_search_url(self, keyword, page):
        if page == 1:
            return await self.fetch(f"{self.base_url}/?s={quote(keyword, safe='')}", timeout=30)
        else:
            return await self.fetch(f"{self.base_url}/page/{page}/?s={quote(keyword, safe='')}", timeout=30)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()

        # RM.ID search returns general articles regardless of query;
        # filter strictly by keyword presence in the visible title.
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if self._article_re.match(href):
                title = a.get_text(strip=True)
                # Use self.keywords from the parent class (set in fetch_search_results caller)
                # For now, use the first keyword from the scraper's keywords list
                kw = self.keywords[0].lower() if self.keywords else ""
                if title and kw and kw in title.lower():
                    links.add(href)

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

        # Date: span with ISO-ish date pattern
        publish_date_str = ""
        for span in soup.select("span"):
            txt = span.get_text(strip=True)
            if re.match(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", txt):
                publish_date_str = txt.split("||")[0].strip()
                break
        if not publish_date_str:
            date_meta = soup.select_one('meta[property="article:published_time"]')
            if date_meta:
                publish_date_str = date_meta.get("content", "")

        content_div = soup.select_one("div.content-berita") or soup.select_one('div[itemprop="articleBody"]') or soup.select_one(".article-content") or soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        publish_date = self.parse_date(publish_date_str)
        if not publish_date:
            logging.debug("RM.ID date parse failed | url: %s | date: %r", link, publish_date_str[:50])
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
            "source": "rmid",
            "link": link,
        }
        await self.queue_.put(item)
