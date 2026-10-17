"""
Tirto scraper — uses Playwright to bypass Cloudflare and capture Google CSE.

Flow: 1) pass Cloudflare challenge on search page, 2) capture CSE results,
3) navigate to article pages from same session (Cloudflare cookie persists).
"""

import json
import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class TirtoScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None, keyword_concurrency=None):
        super().__init__(keywords, concurrency, queue_, keyword_concurrency=keyword_concurrency)
        self.base_url = "https://tirto.id"
        self.start_date = start_date
        self.continue_scraping = True
        self._article_href = re.compile(r"^https?://tirto\.id/[a-z][a-z0-9-]+-[a-z0-9]+$")

    @staticmethod
    async def _validate_listing(page, response):
        if response is None or response.status >= 400:
            status = response.status if response is not None else "no response"
            raise RuntimeError(f"Tirto listing navigation failed: {status}")
        soup = BeautifulSoup(await page.content(), "html.parser")
        title = soup.title.get_text(strip=True).casefold() if soup.title else ""
        if title in {"just a moment...", "attention required! | cloudflare", "access denied", "403 forbidden"} or soup.select_one(
            "#challenge-form, #cf-challenge-running, #challenge-running, .cf-browser-verification"
        ):
            raise RuntimeError("Tirto listing blocked by an access challenge")

    async def _queue_article_from_page(self, page, link, keyword):
        title_el = await page.query_selector("h1")
        title = (await title_el.inner_text()).strip() if title_el else ""
        if not title:
            return
        article_el = await page.query_selector("article") or await page.query_selector(".detail-content")
        if not article_el:
            return
        content = " ".join(
            p.strip() for p in (await article_el.inner_text()).split("\n") if len(p.strip()) > 30
        )
        if not content:
            return
        body_text = await page.evaluate("() => document.body.textContent")
        date_match = re.search(r"(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", body_text)
        publish_date_str = date_match.group(1) if date_match else ""
        publish_date = self.parse_date(publish_date_str, locales=["id"])
        if not publish_date:
            logging.debug("Tirto date parse failed | url: %s | date: %r", link, publish_date_str[:50])
            return
        if self.start_date and publish_date < self.start_date:
            return
        author_match = re.search(r"Penulis[:\s]+([^\n,]+)", body_text)
        author = author_match.group(1).strip() if author_match else "Unknown"
        await self.queue_.put({
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": "Unknown",
            "source": "tirto.id",
            "link": link,
        })

    async def fetch_search_results(self, keyword):
        """Use Playwright: pass Cloudflare, capture CSE, fetch articles."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                # Listen before navigation so initial CSE responses are captured.
                cse_results = []
                async def handle_response(response):
                    if "cse.google.com/cse/element" in response.url:
                        try:
                            body = await response.text()
                            match = re.search(r'google\.search\.cse\.api\d+\((.*)\)', body, re.DOTALL)
                            if match:
                                data = json.loads(match.group(1))
                                cse_results.extend(data.get("results", []))
                        except Exception:
                            pass

                page.on("response", handle_response)
                response = await page.goto(
                    f"{self.base_url}/search?{urlencode({'q': keyword})}",
                    wait_until="domcontentloaded", timeout=30000,
                )
                await page.wait_for_timeout(8000)
                await self._validate_listing(page, response)

                article_links = []
                for r in cse_results:
                    url = r.get("url", "")
                    if self._article_href.match(url) and url not in self.dedup_links and url not in article_links:
                        article_links.append(url)

                if not article_links:
                    logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
                    return

                # Step 3: Navigate to articles from same session (Cloudflare cookie persists)
                for link in article_links:
                    if not self.continue_scraping:
                        break
                    try:
                        await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(3000)

                        await self._queue_article_from_page(page, link, keyword)
                    except Exception as e:
                        logging.debug(f"Tirto article fetch failed for {link}: {e}")

            finally:
                await browser.close()

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def get_article(self, link, keyword):
        pass

    async def fetch_latest_results(self):
        """Override to handle latest extraction entirely in one browser session."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                seen = set(self.dedup_links)

                for p_num in range(1, self.max_latest_pages + 1):
                    if not self.continue_scraping:
                        break

                    # Navigate to homepage or latest index
                    url = self.base_url if p_num == 1 else f"{self.base_url}/indeks"
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(3000)
                    await self._validate_listing(page, response)

                    # Extract article links from the page
                    raw_links = await page.evaluate("""() => {
                        return [...new Set(
                            [...document.querySelectorAll('a[href]')]
                                .map(a => a.href)
                                .filter(h => h.startsWith('https://tirto.id/') && h.match(/-[a-z0-9]+$/))
                        )]
                    }""")

                    links = list(dict.fromkeys(
                        link for link in raw_links
                        if self._article_href.match(link) and link not in seen
                    ))
                    if not links:
                        break
                    seen.update(links)

                    # Navigate to each article and extract content
                    for link in links[:10]:
                        if not self.continue_scraping:
                            break
                        try:
                            await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                            await page.wait_for_timeout(2000)

                            await self._queue_article_from_page(page, link, "latest")
                        except Exception as e:
                            logging.debug(f"Error processing Tirto article {link}: {e}")
            finally:
                await browser.close()

    def build_latest_url(self, page):
        return None

    def parse_latest_article_links(self, response_text):
        return None

