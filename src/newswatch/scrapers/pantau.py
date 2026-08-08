"""
Pantau.com scraper — uses search page with Next.js __NEXT_DATA__ parsing.

https://www.pantau.com/search?q={keyword}
"""

import json
import logging
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class PantauScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.pantau.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10

    async def build_search_url(self, keyword, page):
        # ?page=N returns the same 20 rows as page 1, so there is nothing
        # past the first page to ask for
        if page > 1:
            return None
        url = f"{self.base_url}/search?{urlencode({'q': keyword})}"
        return await self.fetch(url)

    def _extract_next_data(self, response_text):
        """Extract __NEXT_DATA__ JSON from page HTML."""
        soup = BeautifulSoup(response_text, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                return json.loads(script.string)
            except (json.JSONDecodeError, AttributeError):
                pass
        return None

    def parse_article_links(self, response_text):
        data = self._extract_next_data(response_text)
        if not data:
            return None

        articles = data.get("props", {}).get("pageProps", {}).get("articles", [])
        if not articles:
            return None

        # each row carries its own path (/{category}/{id}/{slug}); rebuilding
        # it from category + slug drops the id and lands on a 404
        links = {
            urljoin(self.base_url, article["urlDetail"])
            for article in articles
            if article.get("urlDetail")
        }
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning("No response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")
        data = self._extract_next_data(response_text)

        # Extract content from HTML article element
        content_div = soup.select_one("main article") or soup.select_one("article")
        if content_div:
            for tag in content_div.find_all(["script", "style", "iframe"]):
                tag.extract()
            content = content_div.get_text(separator=" ", strip=True)
        else:
            content = ""

        if not content:
            return

        # Extract metadata from __NEXT_DATA__ if available
        title = ""
        author = "Unknown"
        published_at = ""
        if data:
            page_props = data.get("props", {}).get("pageProps", {})
            article_data = page_props.get("article") or page_props.get("initialArticle")
            if article_data:
                title = (article_data.get("title") or "").strip()
                author_field = article_data.get("createdBy") or article_data.get("author")
                if author_field:
                    if isinstance(author_field, dict):
                        author = author_field.get("name", "Unknown") or "Unknown"
                    elif isinstance(author_field, str):
                        author = author_field.strip() or "Unknown"
                published_at = article_data.get("createdAt") or article_data.get("published_at", "")

        # Fallback title from HTML
        if not title:
            title_el = soup.select_one('meta[property="og:title"]') or soup.select_one("h1")
            title = (title_el.get("content", "").strip()) if title_el and title_el.get("content") else ""
            if not title and title_el:
                title = title_el.get_text(strip=True)
        if not title:
            return

        # Parse date
        publish_date = self.parse_date(published_at) if published_at else None
        if not publish_date:
            logging.debug("Pantau date parse failed | url: %s | date: %r", link, published_at[:50] if published_at else "empty")
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        # Category from URL path
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
            "source": self.base_url.split("www.")[1],
            "link": link,
        }
        await self.queue_.put(item)

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(self.base_url)
        return await self.fetch(f"{self.base_url}/?sort=latest&page={page}")

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        data = self._extract_next_data(response_text)
        if not data:
            return None

        page_props = data.get("props", {}).get("pageProps", {})

        # Homepage/latest pages use different keys than search pages
        articles = (
            page_props.get("articles", [])
            or page_props.get("headline", [])
            or page_props.get("initialNewsFeed", [])
            or page_props.get("editorChoice", [])
            or page_props.get("nonHeadline", [])
            or page_props.get("popular", [])
        )
        if not articles:
            return None

        links = {
            urljoin(self.base_url, article["urlDetail"])
            for article in articles
            if article.get("urlDetail")
        }
        return links or None
