"""
Tribunnews scraper — uses sitemap scanning with keyword filtering.

The search API returns 403, but sitemaps provide article URLs
that can be filtered by keyword presence.
"""

import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TribunnewsScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.tribunnews.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.sitemap_urls = [
            f"{self.base_url}/ekonomi/sitemap-news.xml",
            f"{self.base_url}/ekonomi/sitemap-web.xml",
            f"{self.base_url}/bisnis/sitemap-news.xml",
            f"{self.base_url}/regional/sitemap-news.xml",
            f"{self.base_url}/nasional/sitemap-news.xml",
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    async def fetch_search_results(self, keyword):
        """Scan sitemaps and filter by keyword in URL."""
        kw_lower = keyword.lower()
        all_links = set()

        for sm_url in self.sitemap_urls:
            if not self.continue_scraping:
                break
            try:
                child_text = await self.fetch(sm_url, headers=self.headers, timeout=30)
                if not child_text:
                    continue
                soup = BeautifulSoup(child_text, "xml")
                for loc in soup.find_all("loc"):
                    url = loc.text.strip()
                    if url and kw_lower in url.lower():
                        all_links.add(url)
            except Exception:
                pass

        if all_links:
            for link in list(all_links)[:20]:
                await self._process_article(link, keyword)
        else:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def _process_article(self, link, keyword):
        try:
            response_text = await self.fetch(link, headers=self.headers, timeout=30)
            if not response_text:
                return

            soup = BeautifulSoup(response_text, "html.parser")

            meta_title = soup.find("meta", {"property": "og:title"})
            title = meta_title.get("content", "").strip() if meta_title else ""
            if not title:
                h1 = soup.select_one("h1")
                title = h1.get_text(strip=True) if h1 else ""
            if not title:
                return

            # Date from page text
            publish_date_str = ""
            body_text = soup.get_text(" ", strip=True)
            date_match = re.search(r"(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", body_text)
            if date_match:
                publish_date_str = date_match.group(1)

            # Content
            content_div = soup.select_one("div.side-article.txt-article") or soup.select_one("div.content")
            if not content_div:
                return
            paragraphs = [p.get_text(" ", strip=True) for p in content_div.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                content = content_div.get_text(" ", strip=True)
            if not content:
                return

            # Author from meta or text
            meta_author = soup.find("meta", {"name": "author"})
            author = meta_author.get("content", "Unknown") if meta_author else "Unknown"

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.debug("Tribunnews date parse failed | url: %s | date: %r", link, publish_date_str[:50])
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
                "source": "tribunnews.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def get_article(self, link, keyword):
        await self._process_article(link, keyword)

    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(
            f"{self.base_url}/sitemap-news.xml",
            headers=self.headers,
            timeout=30,
        )

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "xml")
        links = set()
        for loc in soup.find_all("loc"):
            url = loc.text.strip()
            if url and "tribunnews.com" in url:
                links.add(url)
        return links or None
