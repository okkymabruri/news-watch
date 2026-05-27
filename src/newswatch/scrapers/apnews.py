"""
AP News scraper — uses /hub/{topic} topic pages for search, homepage/latest for latest.

AP robots.txt disallows /search?q=*, so we use /hub/{keyword} for keyword queries.
Article pattern: /article/{slug}

Note: AP hub pages return unfiltered results, so we filter by keyword in title/link text.
"""

import json
import logging
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class APNewsScraper(BaseScraper):
    def __init__(self, keywords, concurrency=3, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://apnews.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 3
        self._current_keyword = None
        self._article_re = re.compile(
            r"^https?://(?:www\.)?apnews\.com/article/.+$"
        )

    async def build_search_url(self, keyword, page):
        # Store keyword for filtering in parse_article_links
        self._current_keyword = keyword
        safe_kw = quote(keyword.replace(" ", "-").lower(), safe="")
        if page > 1:
            url = f"{self.base_url}/hub/{safe_kw}/page-{page}"
        else:
            url = f"{self.base_url}/hub/{safe_kw}"
        return await self.fetch(url, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")

        all_links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                if not any(p in full_url for p in ["/podcast", "/newsletter", "/photo", "/buyline"]):
                    all_links.add(full_url)

        # AP hub pages are unfiltered — filter by keyword in URL or title text
        kw = self._current_keyword
        if kw:
            kw_lower = kw.lower()
            title_map = {}
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
                if full_url in all_links:
                    title_map[full_url] = a.get_text(" ", strip=True).lower()

            filtered = set()
            for url in all_links:
                if kw_lower in url.lower() or kw_lower in title_map.get(url, ""):
                    filtered.add(url)
            return filtered or None

        return all_links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
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

        # Content
        content_div = soup.select_one("div.RichTextStoryBody")
        if not content_div:
            content_div = soup.select_one("div.Article")
        if not content_div:
            content_div = soup.select_one("div[class*='article-body']")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        for tag in content_div.find_all(
            ["section", "div"],
            class_=re.compile(r"RelatedContent|recommended|newsletter|share|social|ad|subscribe", re.IGNORECASE),
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
        category = parts[1] if len(parts) > 1 else "News"

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "apnews.com",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        date_meta = soup.select_one('meta[property="article:published_time"]')
        if date_meta and date_meta.get("content"):
            parsed = self.parse_date(date_meta["content"])
            if parsed:
                return parsed

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

        time_el = soup.select_one("time[datetime]")
        if time_el:
            parsed = self.parse_date(time_el["datetime"])
            if parsed:
                return parsed

        logging.debug("AP News date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        author_meta = soup.select_one('meta[name="author"]')
        if author_meta and author_meta.get("content"):
            return author_meta["content"].strip()

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
                        names = [a.get("name", "") for a in author_data if a.get("name")]
                        if names:
                            return ", ".join(names)
                except (json.JSONDecodeError, AttributeError, IndexError):
                    continue

        return "Unknown"

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(f"{self.base_url}/hub/apf-topnews", timeout=30)
        return await self.fetch(f"{self.base_url}/hub/apf-topnews/page-{page}", timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                if not any(p in full_url for p in ["/podcast", "/newsletter", "/photo", "/buyline"]):
                    links.add(full_url)
        return links or None
