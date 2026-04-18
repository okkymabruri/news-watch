"""
Tirto scraper — uses Playwright to bypass Cloudflare and capture Google CSE.

Flow: 1) pass Cloudflare challenge on search page, 2) capture CSE results,
3) navigate to article pages from same session (Cloudflare cookie persists).
"""

import json
import logging
import re

from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class TirtoScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://tirto.id"
        self.start_date = start_date
        self.continue_scraping = True
        self._article_href = re.compile(r"^https?://tirto\.id/[a-z][a-z0-9-]+-[a-z0-9]+$")

    async def fetch_search_results(self, keyword):
        """Use Playwright: pass Cloudflare, capture CSE, fetch articles."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                # Step 1: Pass Cloudflare challenge
                await page.goto(f"{self.base_url}/search?q={keyword}", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                # Step 2: Capture CSE results
                cse_results = []
                async def handle_response(response):
                    if "cse.google.com/cse/element" in response.url:
                        try:
                            body = await response.text()
                            match = re.search(r'google\.search\.cse\.api\d+\((.*)\)', body, re.DOTALL)
                            if match:
                                data = json.loads(match.group(1))
                                cse_results.extend(data.get("results", []))
                        except:
                            pass

                page.on("response", handle_response)
                # Reload to capture CSE
                await page.reload(wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(8000)

                article_links = []
                for r in cse_results:
                    url = r.get("url", "")
                    if self._article_href.match(url):
                        article_links.append(url)

                if not article_links:
                    logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
                    return

                # Step 3: Navigate to articles from same session (Cloudflare cookie persists)
                for link in article_links[:20]:
                    if not self.continue_scraping:
                        break
                    try:
                        await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(3000)

                        title_el = await page.query_selector("h1")
                        title = await title_el.inner_text() if title_el else ""
                        title = title.strip()
                        if not title:
                            continue

                        article_el = await page.query_selector("article") or await page.query_selector(".detail-content")
                        if not article_el:
                            continue

                        content = await article_el.inner_text()
                        content = " ".join([p.strip() for p in content.split("\n") if len(p.strip()) > 30])
                        if not content:
                            continue

                        # Extract date from page text
                        body_text = await page.evaluate("() => document.body.textContent")
                        date_match = re.search(r"(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", body_text)
                        publish_date_str = date_match.group(1) if date_match else ""

                        publish_date = self.parse_date(publish_date_str, locales=["id"])
                        if not publish_date:
                            logging.debug("Tirto date parse failed | url: %s | date: %r", link, publish_date_str[:50])
                            continue

                        if self.start_date and publish_date < self.start_date:
                            self.continue_scraping = False
                            continue

                        # Extract author from page
                        author_match = re.search(r"Penulis[:\s]+([^\n,]+)", body_text)
                        author = author_match.group(1).strip() if author_match else "Unknown"

                        item = {
                            "title": title,
                            "publish_date": publish_date,
                            "author": author,
                            "content": content,
                            "keyword": keyword,
                            "category": "Unknown",
                            "source": "tirto.id",
                            "link": link,
                        }
                        await self.queue_.put(item)
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
