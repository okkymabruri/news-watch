"""DDTC News scraper with browser-rendered keyword search."""

import logging
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .basescraper import BaseScraper

BASE_URL = "https://news.ddtc.co.id"
ARTICLE_RE = re.compile(
    r"^https://news\.ddtc\.co\.id/(?:berita|review|literasi|komunitas)/.+/\d+/.+"
)


def _normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _matches_keyword(keyword, title):
    tokens = [token for token in _normalize(keyword).split() if len(token) > 1]
    if not tokens:
        return True
    haystack = _normalize(title)
    return all(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)


class DDTCNewsScraper(BaseScraper):
    """Scrape DDTC News search results and article pages."""

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = BASE_URL
        self.start_date = start_date
        self.max_pages = 10
        self.max_latest_pages = 1
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            )
        }

    async def fetch_search_results(self, keyword):
        """Render client-side results and expand bounded pagination."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=self.headers["User-Agent"])
                page = await context.new_page()
                url = f"{BASE_URL}/search/?q={quote(keyword, safe='')}"
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_selector("div.news-item a[href]", timeout=20_000)
                await page.wait_for_timeout(5_000)

                previous_count = await page.locator("div.news-item a[href]").count()
                for _ in range(self.max_pages - 1):
                    button = page.get_by_role("button", name="Muat Lebih Banyak")
                    if await button.count() == 0:
                        break
                    await button.click(timeout=10_000)
                    try:
                        await page.wait_for_function(
                            "count => document.querySelectorAll('div.news-item a[href]').length > count",
                            previous_count,
                            timeout=10_000,
                        )
                    except PlaywrightTimeoutError as error:
                        logging.debug("DDTC load-more stopped for %r: %s", keyword, error)
                        break
                    current_count = await page.locator("div.news-item a[href]").count()
                    if current_count <= previous_count:
                        break
                    previous_count = current_count

                links = self.parse_article_links(await page.content(), keyword)
                if links:
                    await self.process_page(links, keyword)
                else:
                    logging.info("No news found on %s for keyword: %r", BASE_URL, keyword)
            finally:
                await browser.close()

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text, keyword=None):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for anchor in soup.select("div.news-item a[href]"):
            link = urljoin(BASE_URL, anchor.get("href", ""))
            title = anchor.get_text(" ", strip=True)
            if ARTICLE_RE.match(link) and _matches_keyword(keyword, title):
                links.add(link)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            return
        soup = BeautifulSoup(response_text, "html.parser")

        title_meta = soup.select_one('meta[property="og:title"]')
        title_node = soup.select_one("h1")
        title = (
            title_meta.get("content", "").strip()
            if title_meta
            else title_node.get_text(" ", strip=True) if title_node else ""
        )
        date_node = soup.select_one("#publish-news")
        body_node = soup.select_one("div.contentArticle")
        if not title or not date_node or not body_node:
            return

        publish_text = date_node.get_text(" ", strip=True).replace("Jum'at", "Jumat")
        publish_date = self.parse_date(publish_text, locales=["id"])
        if not publish_date:
            logging.error("DDTC date parse failed | url: %s | date: %r", link, publish_text)
            return
        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        for noise in body_node.select("script, style, noscript, iframe"):
            noise.extract()
        content = " ".join(
            text for paragraph in body_node.select("p")
            if (text := paragraph.get_text(" ", strip=True))
        )
        if not content:
            return

        author_meta = soup.select_one('meta[name="author"]')
        category_meta = soup.select_one('meta[name="category"]')
        await self.queue_.put(
            {
                "title": title,
                "publish_date": publish_date,
                "author": author_meta.get("content", "Unknown").strip() if author_meta else "Unknown",
                "content": content,
                "keyword": keyword,
                "category": category_meta.get("content", "Unknown").strip() if category_meta else "Unknown",
                "source": "news.ddtc.co.id",
                "link": link,
            }
        )

    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(BASE_URL, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = {
            urljoin(BASE_URL, anchor.get("href", ""))
            for anchor in soup.select("a[href]")
            if ARTICLE_RE.match(urljoin(BASE_URL, anchor.get("href", "")))
        }
        return links or None
