"""
The Jakarta Post scraper — uses Playwright to bootstrap Google CSE search.

Same CSE provider as Suara; direct HTTP requests to CSE fail without browser session.
Route interception captures results without needing explicit token capture.
"""

import json
import logging
import re

import aiohttp
from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class JakartaPostScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.thejakartapost.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_href = re.compile(
            r"^https?://(?:www\.)?thejakartapost\.com/.+/20\d{2}/\d{2}/\d{2}/.+"
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

                    async def handle_route(route):
                        if "cse/element/v1" in route.request.url:
                            response = await route.fetch()
                            body = await response.text()
                            cse_body.append(body)
                        await route.continue_()

                    await page.route("**/cse.google.com/**", handle_route)

                    try:
                        await page.goto(search_url, wait_until="load", timeout=20000)
                        await page.wait_for_timeout(5000)
                    except Exception as e:
                        logging.debug("Jakarta Post page load failed for '%s': %s", keyword, e)

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
                    next_url = f"{self.base_url}/search?{search_qs}"

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
            meta_title = soup.find("meta", {"property": "og:title"})
            if meta_title and meta_title.get("content"):
                title = meta_title["content"].split(" - ")[0].strip()
            else:
                title_el = soup.select_one("h1.tjp-title--single")
                title = title_el.get_text(strip=True) if title_el else ""

            if not title:
                h1_elems = soup.find_all("h1")
                for h in h1_elems:
                    text = h.get_text(strip=True)
                    if text and text != "TheJakartaPost" and len(text) > 10:
                        title = text
                        break

            if not title:
                return

            date_elem = soup.select_one(".tjp-single__head .created")
            publish_date_str = ""
            if date_elem:
                full_text = date_elem.get_text(strip=True)
                # Try ISO format first: "Published on 2025-09-29T17:09:28+07:00"
                match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", full_text)
                if match:
                    publish_date_str = match.group().replace("T", " ")
                else:
                    # Fallback: "Published on Sep. 29, 2025" or "Published on September 29, 2025"
                    match = re.search(r"Published\s+on\s+(.+)", full_text, re.IGNORECASE)
                    if match:
                        publish_date_str = match.group(1).strip()

            content_div = soup.select_one(".tjp-single__content") or soup.select_one("article")
            if not content_div:
                return

            for tag in content_div.find_all(["div", "script", "style"]):
                classes = tag.get("class", [])
                if tag and any(
                    "ad" in cls.lower()
                    or "related" in cls.lower()
                    or "popular" in cls.lower()
                    or "newsletter" in cls.lower()
                    for cls in classes
                ):
                    tag.extract()
            content = content_div.get_text(separator=" ", strip=True)
            if not content:
                return

            author_elem = soup.select_one(".author")
            author = author_elem.get_text(strip=True) if author_elem else "Unknown"

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.debug(
                    "Jakarta Post date parse failed | url: %s | date: %r",
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
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "thejakartapost.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)

    def _get_soup(self, text):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "html.parser")

    async def build_latest_url(self, page):
        if page > 1:
            return None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                pg = await context.new_page()
                await pg.goto(self.base_url, wait_until="load", timeout=20000)
                await pg.wait_for_timeout(5000)
                return await pg.content()
            finally:
                await browser.close()

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = self._get_soup(response_text)
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if self._article_href.match(href):
                links.add(href)
        return links or None
