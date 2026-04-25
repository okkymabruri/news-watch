"""
TVRI News scraper — uses sitemap scanning with keyword filtering.

The API requires authentication, but sitemaps provide article URLs
that can be filtered by keyword presence.
"""

import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TVRINewsScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://tvrinews.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.sitemap_urls = [
            "https://ekonomi.tvrinews.com/sitemap/news.xml",
            "https://ekonomi.tvrinews.com/sitemap/web.xml",
            "https://nasional.tvrinews.com/sitemap/news.xml",
            "https://daerah.tvrinews.com/sitemap/news.xml",
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    async def fetch_search_results(self, keyword):
        """Scan sitemaps and filter by keyword in URL."""
        kw_lower = keyword.lower()
        all_links = set()

        for sm_url in self.sitemap_urls:
            try:
                response_text = await self.fetch(sm_url, headers=self.headers, timeout=30)
                if not response_text:
                    continue
                soup = BeautifulSoup(response_text, "xml")
                for loc in soup.find_all("loc"):
                    url = loc.text.strip()
                    if url and kw_lower in url.lower():
                        all_links.add(url)
            except Exception as e:
                logging.debug(f"TVRI sitemap fetch failed for {sm_url}: {e}")

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
                return

            # Date from various sources
            publish_date_str = ""
            meta_date = soup.find("meta", {"property": "article:published_time"})
            if meta_date and meta_date.get("content"):
                publish_date_str = meta_date.get("content")
            else:
                # Try to find date in page text
                for el in soup.find_all(string=True):
                    text = el.strip()
                    if re.search(r"\d{1,2}\s+[A-Z][a-z]+\s+\d{4}", text):
                        date_match = re.search(r"(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", text)
                        if date_match:
                            publish_date_str = date_match.group(1)
                            break

            content_div = soup.select_one("div.blog-content") or soup.select_one("article")
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
                logging.debug("TVRI date parse failed | url: %s | date: %r", link, publish_date_str[:50])
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
                "source": "tvrinews.com",
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
