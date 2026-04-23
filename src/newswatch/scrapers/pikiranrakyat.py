"""
Pikiran Rakyat scraper — uses Playwright to bootstrap Google CSE search.

Search page is protected by Cloudflare 1015 rate limiting.
CSE interception captures article URLs after CF challenge is passed.
"""

import json
import logging
import re

import aiohttp
from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class PikiranRakyatScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.pikiran-rakyat.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_href = re.compile(
            r"^https?://(?:[\w-]+\.)?pikiran-rakyat\.com/[^/]+/pr-\d+/"
        )

    async def fetch_search_results(self, keyword):
        """Use Playwright to pass Cloudflare, then extract CSE results."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                search_url = f"{self.base_url}/search/?q={keyword}"

                for pg in range(1, self.max_pages + 1):
                    if not self.continue_scraping:
                        break

                    cse_body = []

                    async def handle_route(route):
                        if "cse/element/v1" in route.request.url:
                            response = await route.fetch()
                            body = await response.text()
                            cse_body.append(body)
                        await route.continue_()

                    await page.route("**/cse.google.com/**", handle_route)

                    try:
                        await page.goto(search_url, wait_until="load", timeout=20000)
                        await page.wait_for_timeout(3000)
                    except Exception as e:
                        logging.debug("PR page load failed for '%s': %s", keyword, e)

                    await page.unroute("**/cse.google.com/**", handle_route)

                    if not cse_body:
                        break

                    article_links, next_url = self._extract_links_and_next(cse_body, keyword)
                    if not article_links:
                        break

                    await self.process_page(list(article_links), keyword)

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
            return json.loads(match.group(1))
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

            if not next_url:
                queries = parsed.get("queries", {})
                next_page = queries.get("nextPage", [])
                if next_page:
                    params = next_page[0]
                    start = params.get("startIndex", 1)
                    search_qs = f"q={keyword}&start={start}"
                    next_url = f"{self.base_url}/search/?{search_qs}"

        return links, next_url

    # Fallbacks to satisfy BaseScraper abstract methods
    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def get_article(self, link, keyword):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
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
                title_meta = soup.select_one('meta[property="og:title"]')
                title = title_meta.get("content", "") if title_meta else ""
            if not title:
                return

            date_el = soup.select_one("span.mt-10") or soup.select_one("span[class*='date']")
            publish_date_str = date_el.get_text(strip=True) if date_el else ""
            if "|" in publish_date_str:
                publish_date_str = publish_date_str.split("|")[0].strip()

            content_el = soup.select_one("div.read__article") or soup.select_one("article.read__content") or soup.select_one('div[itemprop="articleBody"]')
            if not content_el:
                return

            paragraphs = [p.get_text(" ", strip=True) for p in content_el.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                content = content_el.get_text(separator=" ", strip=True)
            if not content:
                return

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.debug(
                    "PR date parse failed | url: %s | date: %r",
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
                "source": "pikiranrakyat",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)

    def _get_soup(self, text):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "html.parser")
