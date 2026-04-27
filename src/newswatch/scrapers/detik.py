"""
Detik scraper — uses sitemap scanning with keyword filtering.

The search API is unreliable, but sitemaps provide article URLs
that can be filtered by keyword presence in the URL.
"""

import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class DetikScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.detik.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.sitemap_urls = [
            "https://finance.detik.com/sitemap_news.xml",
            "https://news.detik.com/berita/sitemap_news.xml",
            "https://news.detik.com/ekonomi/sitemap_news.xml",
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }
        self.latest_href_pattern = re.compile(
            r"^https://news\.detik\.com/.+/d-\d+/"
        )

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
                logging.debug(f"Detik sitemap fetch failed for {sm_url}: {e}")

        if all_links:
            for link in list(all_links):
                await self.get_article(link, keyword)
        else:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def build_latest_url(self, page):
        return await self.fetch(
            f"https://news.detik.com/indeks?page={page}",
            headers=self.headers,
            timeout=30,
        )

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        filtered_hrefs = {
            a.get("href")
            for a in soup.select("article a[href]")
            if a.get("href")
            and self.latest_href_pattern.match(a.get("href"))
            and "20.detik.com" not in a.get("href")
            and "/foto-" not in a.get("href")
        }
        return filtered_hrefs or None

    async def get_article(self, link, keyword):
        try:
            response_text = await self.fetch(link, headers=self.headers, timeout=30)
            if not response_text:
                return

            soup = BeautifulSoup(response_text, "html.parser")

            title_el = soup.select_one("h1.detail__title") or soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                return

            date_el = soup.select_one("div.detail__date")
            publish_date_str = date_el.get_text(strip=True) if date_el else ""

            content_div = soup.select_one("div.detail__body-text") or soup.select_one("article")
            if not content_div:
                return
            paragraphs = [p.get_text(" ", strip=True) for p in content_div.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                content = content_div.get_text(" ", strip=True)
            if not content:
                return

            author_el = soup.select_one("div.detail__author")
            author = author_el.get_text(strip=True) if author_el else "Unknown"

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.debug("Detik date parse failed | url: %s | date: %r", link, publish_date_str[:50])
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            category = "Unknown"
            cat_el = soup.select_one("div.detail__category a")
            if cat_el:
                category = cat_el.get_text(strip=True)

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "detik.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
