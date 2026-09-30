"""
Galamedia scraper — uses search page with keyword filtering.

https://galamedia.pikiran-rakyat.com/search?q={keyword}

Note: tag/{keyword} endpoint has stale content; search page returns fresher results.
"""

from contextvars import ContextVar
import logging
import re
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_search_mode: ContextVar[bool] = ContextVar("galamedia_search_mode", default=False)


class GalamediaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://galamedia.pikiran-rakyat.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(r"/\w+/pr-\d+/[^/]+/?")
        self._date_re = re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)\w*\s+(\d{4})")

    async def build_search_url(self, keyword, page):
        if page == 1:
            url = f"{self.base_url}/search?q={quote(keyword, safe='')}"
        else:
            url = f"{self.base_url}/search?q={quote(keyword, safe='')}&page={page}"
        return await self.fetch(url, timeout=30)

    def _article_url(self, href):
        url = urljoin(self.base_url + "/", href)
        parts = urlsplit(url)
        if (parts.scheme in ("http", "https")
                and parts.netloc == "galamedia.pikiran-rakyat.com"
                and not parts.query and not parts.fragment
                and self._article_re.fullmatch(parts.path)):
            return url
        return None

    def parse_article_links(self, response_text, keyword=None):
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        keyword = keyword if keyword is not None else (self.keywords[0] if self.keywords else "")

        for item in soup.select("div.latest__item"):
            for a in item.select("a[href]"):
                url = self._article_url(a["href"])
                title = a.get_text(strip=True)
                if url and title and keyword and keyword.lower() in title.lower():
                    links.add(url)

        return links or None

    async def fetch_search_results(self, keyword):
        # Keep the keyword local to this task: BaseScraper runs keyword searches concurrently.
        token = _search_mode.set(True)
        try:
            page = 1
            self._reset_pagination()
            while self.max_pages is None or page <= self.max_pages:
                response_text = await self.build_search_url(keyword, page)
                if not response_text:
                    break
                links = self.parse_article_links(response_text, keyword=keyword)
                if not links:
                    break
                in_window = await self.process_page(links, keyword)
                if not self._keep_paginating(in_window):
                    break
                page += 1
        finally:
            _search_mode.reset(token)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title_elem = soup.select_one("h1") or soup.select_one('meta[property="og:title"]')
        title = (title_elem.get("content", "") or title_elem.get_text(strip="")) if title_elem else ""
        if not title or ((_search_mode.get() or keyword != "latest")
                         and keyword.lower() not in title.lower()):
            return

        author_elem = soup.select_one('meta[name="author"]') or soup.select_one(".author")
        author = (author_elem.get("content", "") or author_elem.get_text(strip="")) if author_elem else "Unknown"

        # Date: span with Indonesian date pattern inside article
        publish_date_str = ""
        for span in soup.select("span"):
            txt = span.get_text(strip=True)
            m = self._date_re.search(txt)
            if m:
                publish_date_str = m.group(0)
                break
        if not publish_date_str:
            return

        content_div = soup.select_one("div.read__article") or soup.select_one("article.read__content") or soup.select_one('div[itemprop="articleBody"]')
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        publish_date = self.parse_date(publish_date_str, locales=["id"])
        if not publish_date:
            logging.debug("Galamedia date parse failed | url: %s | date: %r", link, publish_date_str[:50])
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
            "source": "galamedia",
            "link": link,
        }
        await self.queue_.put(item)

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(self.base_url, timeout=30)
        else:
            return await self.fetch(f"{self.base_url}/?page={page}", timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for item in soup.select("div.latest__item"):
            for a in item.select("a[href]"):
                url = self._article_url(a["href"])
                if url:
                    links.add(url)
        return links or None
