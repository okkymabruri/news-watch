"""
Kumparan scraper — uses sitemap scanning with keyword filtering.

No search API available, but sitemaps provide article URLs
that can be filtered by keyword presence.
"""

import logging
import re

import aiohttp
from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class KumparanScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://kumparan.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.sitemap_index = f"{self.base_url}/sitemap.xml"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    async def fetch_search_results(self, keyword):
        """Scan all child sitemaps and filter by keyword in URL."""
        kw_lower = keyword.lower()
        all_links = set()

        # Get sitemap index
        index_text = await self.fetch(self.sitemap_index, headers=self.headers, timeout=30)
        if not index_text:
            return

        index_soup = BeautifulSoup(index_text, "xml")
        child_sitemaps = [loc.text.strip() for loc in index_soup.find_all("loc") if loc.text and "sitemap" in loc.text.lower()]

        for sm_url in child_sitemaps:
            try:
                child_text = await self.fetch(sm_url, headers=self.headers, timeout=30)
                if not child_text:
                    continue
                soup = BeautifulSoup(child_text, "xml")
                for loc in soup.find_all("loc"):
                    url = loc.text.strip()
                    if url and kw_lower in url.lower():
                        all_links.add(url)
            except Exception as e:
                logging.debug(f"Kumparan sitemap fetch failed for {sm_url}: {e}")

        if all_links:
            for link in list(all_links):
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

            meta_date = soup.find("meta", {"property": "article:published_time"})
            publish_date_str = meta_date.get("content", "") if meta_date else ""

            content_div = soup.select_one("div.article-content") or soup.select_one("article")
            if not content_div:
                return
            paragraphs = [p.get_text(" ", strip=True) for p in content_div.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                content = content_div.get_text(" ", strip=True)
            if not content:
                return

            meta_author = soup.find("meta", {"name": "author"})
            author = meta_author.get("content", "Unknown") if meta_author else "Unknown"

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.debug("Kumparan date parse failed | url: %s | date: %r", link, publish_date_str[:50])
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            category = "Unknown"
            path = link.replace(self.base_url, "").strip("/")
            parts = path.split("/")
            if parts:
                category = parts[0]

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "kumparan.com",
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
        pass
