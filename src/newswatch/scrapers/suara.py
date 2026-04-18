"""
Suara.com scraper — uses Playwright to bootstrap Google CSE search.

The CSE endpoint requires a real browser session (cookies, session state).
Direct HTTP requests get 403.
"""

import json
import logging
import re

import aiohttp
from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class SuaraScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.suara.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_href = re.compile(
            r"^https?://(?:[\w-]+\.)?suara\.com/.+/20\d{2}/\d{2}/\d{2}/.+"
        )

    async def fetch_search_results(self, keyword):
        """Use Playwright to capture Google CSE search results with pagination."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                search_url = f"{self.base_url}/search?q={keyword}"

                for pg in range(1, self.max_pages + 1):
                    if not self.continue_scraping:
                        break

                    cse_body = []
                    seen_urls = set()

                    async def handle_route(route):
                        response = await route.fetch()
                        body = await response.text()
                        cse_body.append(body)
                        await route.fulfill(response=response)

                    await page.route("**/cse.google.com/**", handle_route)

                    try:
                        await page.goto(search_url, wait_until="load", timeout=20000)
                        await page.wait_for_timeout(3000)
                    except Exception as e:
                        logging.debug("Suara page load failed for '%s': %s", keyword, e)

                    await page.unroute("**/cse.google.com/**", handle_route)

                    if not cse_body:
                        break

                    article_links, next_url = self._extract_links_and_next(cse_body, keyword)
                    new_links = article_links - seen_urls if article_links else set()
                    if not new_links:
                        break

                    await self.process_page(list(new_links), keyword)
                    seen_urls.update(new_links)

                    if next_url:
                        search_url = next_url
                    else:
                        break

            finally:
                await browser.close()

    def _parse_cse_body(self, text):
        match = re.search(r"google\.search\.cse\.api\d+\((.*)\)", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
            return data
        except json.JSONDecodeError:
            return None

    def _extract_links_and_next(self, cse_bodies, keyword):
        links = set()
        next_url = None
        for body in cse_bodies:
            parsed = self._parse_cse_body(body)
            if not parsed:
                continue
            for r in parsed.get("results", []):
                url = r.get("url", "")
                if self._article_href.match(url):
                    links.add(url)

            queries = parsed.get("queries", {})
            next_page = queries.get("nextPage", [])
            if next_page and not next_url:
                params = next_page[0]
                start = params.get("startIndex", 1)
                search_qs = f"q={keyword}&start={start}"
                next_url = f"{self.base_url}/search?{search_qs}"

        return links, next_url

    def _extract_links(self, cse_bodies):
        links = set()
        for body in cse_bodies:
            results = self._parse_cse_body(body)
            if not results:
                continue
            for r in results:
                url = r.get("url", "")
                if self._article_href.match(url):
                    links.add(url)
        return links if links else None

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

            date_el = soup.select_one("span.mt-10")
            if not date_el:
                date_el = soup.select_one("span[class*='date']")
            publish_date_str = date_el.get_text(strip=True) if date_el else ""
            publish_date_str = publish_date_str.split("|")[0].strip() if "|" in publish_date_str else publish_date_str
            publish_date_str = publish_date_str.replace("Jum'at", "Jumat")

            content_el = soup.select_one("div.article-content")
            if not content_el:
                content_el = soup.select_one("div.detail-content")
            if not content_el:
                return

            # Extract paragraphs only
            paragraphs = [p.get_text(" ", strip=True) for p in content_el.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                return

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.debug(
                    "Suara date parse failed | url: %s | date: %r",
                    link,
                    publish_date_str[:50],
                )
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
                "author": "Unknown",
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "suara.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)

    def _get_soup(self, text):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "html.parser")
