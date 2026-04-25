"""
Liputan6 scraper — uses Playwright to render /tag/{keyword} pages.

The tag page requires JS rendering. Results are filtered by keyword
presence in the URL to eliminate fallback/leakage articles.
"""

import logging
import re

import aiohttp
from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class Liputan6Scraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.liputan6.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 5
        self._article_href = re.compile(r"^https?://www\.liputan6\.com/.+/read/\d+/?.*")

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

                raw_links = await page.evaluate("""() => {
                    return [...new Set(
                        [...document.querySelectorAll('a[href]')]
                            .filter(a => a.href.includes('/read/'))
                            .map(a => a.href)
                    )]
                }""")

                # Filter: only keep links where keyword appears in URL
                kw_lower = keyword.lower()
                article_links = [
                    link
                    for link in raw_links
                    if self._article_href.match(link)
                    and kw_lower in link.lower()
                    and "/photo/" not in link
                ]

                if article_links:
                    await self.process_page(article_links, keyword)
                else:
                    logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

            finally:
                await browser.close()

    # Fallbacks to satisfy BaseScraper abstract methods
    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def get_article(self, link, keyword):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
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
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                return

            publish_date_str = ""
            meta_time = soup.select_one("meta[property='article:published_time']")
            if meta_time and meta_time.get("content"):
                publish_date_str = meta_time.get("content")

            author = "Unknown"
            meta_author = soup.select_one("meta[name='author']")
            if meta_author and meta_author.get("content"):
                author = meta_author.get("content").strip() or author

            category = "Unknown"
            meta_section = soup.select_one("meta[property='article:section']")
            if meta_section and meta_section.get("content"):
                category = meta_section.get("content").strip() or category

            content_root = (
                soup.select_one("div.article-content-body")
                or soup.select_one("div.article-content-body__item-content")
                or soup.select_one("article")
            )
            if not content_root:
                return

            for tag in content_root.find_all(["script", "style"]):
                tag.extract()

            paragraphs = [p.get_text(" ", strip=True) for p in content_root.find_all("p")]
            paragraphs = [p for p in paragraphs if p]
            content = "\n".join(paragraphs).strip() if paragraphs else ""
            if not content:
                content = content_root.get_text(separator="\n", strip=True)
            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.debug(
                    "Liputan6 date parse failed | url: %s | date: %r",
                    link,
                    publish_date_str[:50],
                )
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "liputan6.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)

    def _get_soup(self, text):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "html.parser")
