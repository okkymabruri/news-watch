"""
Republika scraper — uses Playwright to render /tag/{keyword} pages.

The tag page returns query-specific articles. Results are filtered by
keyword presence in the URL to eliminate fallback/leakage articles.
"""

import logging
import re

import aiohttp
from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class RepublikaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.republika.co.id"
        self.start_date = start_date
        self.continue_scraping = True
        self._article_href = re.compile(r"^https?://[\w.-]*republika\.co\.id/.+/berita/.+")

    async def fetch_search_results(self, keyword):
        """Use Playwright to render tag page, filter by keyword in URL."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                tag_url = f"{self.base_url}/tag/{keyword.lower()}"

                await page.goto(tag_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(5000)

                # Detect no-result page by title
                title = await page.title()
                if "Topic" not in title:
                    logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
                    return

                raw_links = await page.evaluate("""() => {
                    return [...new Set(
                        [...document.querySelectorAll('a[href]')]
                            .filter(a => a.href.includes('/berita/'))
                            .map(a => a.href)
                    )]
                }""")

                # Filter: only keep links where keyword appears in URL
                kw_lower = keyword.lower()
                article_links = [
                    link for link in raw_links if kw_lower in link.lower()
                ]

                if article_links:
                    await self.process_page(article_links, keyword)
                else:
                    logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

            finally:
                await browser.close()

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def get_article(self, link, keyword):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(link, headers=headers) as resp:
                    if resp.status != 200:
                        return
                    response_text = await resp.text()
        except Exception as e:
            logging.error("Error fetching article %s: %s", link, e)
            return

        if not response_text:
            return

        soup = self._get_soup(response_text)
        try:
            # Title from og:title (h1 is empty on Republika)
            meta_title = soup.find("meta", {"property": "og:title"})
            title = meta_title.get("content", "").strip() if meta_title else ""
            if not title:
                h1 = soup.select_one("h1")
                title = h1.get_text(strip=True) if h1 else ""
            if not title:
                return

            # Date from article:published_time meta
            meta_time = soup.find("meta", {"property": "article:published_time"})
            publish_date_str = ""
            if meta_time and meta_time.get("content"):
                publish_date_str = meta_time.get("content")

            # Content from article-content div
            content_div = soup.select_one("div.article-content")
            if not content_div:
                content_div = soup.select_one("article")
            if not content_div:
                return

            paragraphs = [p.get_text(" ", strip=True) for p in content_div.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                content = content_div.get_text(" ", strip=True)
            if not content:
                return

            author = "Unknown"

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.debug("Republika date parse failed | url: %s | date: %r", link, publish_date_str[:50])
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
                "source": "republika.co.id",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)

    def _get_soup(self, text):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "html.parser")
