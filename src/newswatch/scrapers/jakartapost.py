import asyncio
import json
import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class JakartaPostScraper(BaseScraper):
    """
    The Jakarta Post scraper implementation.

    Uses Playwright to render the search page, extract a fresh
    Google CSE token, then queries CSE API with date sorting
    for true keyword search capability.
    """

    CX = "007685728690098461931:2lpamdk7yne"

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "thejakartapost.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        self._token = None

    async def _get_cse_token(self):
        if self._token:
            return self._token

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logging.error(
                "Playwright not installed; install with: playwright install chromium"
            )
            return None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            token_future = asyncio.Future()

            async def handle_request(request):
                if "cse.google.com/cse/element/v1" in request.url:
                    from urllib.parse import parse_qs, urlparse

                    parsed = urlparse(request.url)
                    qs = parse_qs(parsed.query)
                    if "cse_tok" in qs:
                        if not token_future.done():
                            token_future.set_result(qs["cse_tok"][0])

            page.on("request", handle_request)

            try:
                await page.goto(
                    "https://www.thejakartapost.com/search?q=test", timeout=15000
                )
                try:
                    self._token = await asyncio.wait_for(token_future, timeout=10)
                except asyncio.TimeoutError:
                    logging.warning("Failed to capture CSE token from Jakarta Post")
                    self._token = None
            except Exception as e:
                logging.warning(f"Jakarta Post Playwright navigation failed: {e}")
                self._token = None
            finally:
                page.remove_listener("request", handle_request)
                await browser.close()

        return self._token

    async def build_search_url(self, keyword, page):
        token = await self._get_cse_token()
        if not token:
            return None

        cse_url = (
            f"https://cse.google.com/cse/element/v1?"
            f"rsz=filtered_cse&num=10&hl=en&source=gcsc"
            f"&cselibv=dc329f57de078f5d"
            f"&cx={self.CX}"
            f"&q={quote(keyword)}"
            f"&safe=off"
            f"&cse_tok={token}"
            f"&sort=date"
            f"&filter=0"
            f"&start={(page - 1) * 10}"
            f"&as_sitesearch={self.base_url}"
            f"&callback=google.search.cse.api{page}"
        )
        return await self.fetch(cse_url, headers=self.headers, timeout=15)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        match = re.search(
            r"google\.search\.cse\.api\d+\((.*)\)", response_text, re.DOTALL
        )
        if not match:
            return None

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

        results = data.get("results", [])
        if not results:
            return None

        filtered_hrefs = set()
        for r in results:
            url = r.get("url", "")
            if url and self.base_url in url:
                filtered_hrefs.add(url)

        return filtered_hrefs if filtered_hrefs else None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")

        try:
            category = ""
            meta_title = soup.find("meta", {"property": "og:title"})
            if meta_title and meta_title.get("content"):
                title = meta_title["content"].split(" - ")[0].strip()
            else:
                title_elem = soup.select_one("h1.tjp-title--single")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    h1_elems = soup.find_all("h1")
                    for h in h1_elems:
                        text = h.get_text(strip=True)
                        if text and text != "TheJakartaPost" and len(text) > 10:
                            title = text
                            break
                    else:
                        logging.error(f"JakartaPost title not found for article {link}")
                        return

            if not title:
                logging.error(f"JakartaPost title not found for article {link}")
                return

            author = "Unknown"
            author_elem = soup.select_one(".author")
            if author_elem:
                author = author_elem.get_text(strip=True)

            publish_date_str = ""
            date_elem = soup.select_one(".tjp-single__head .created")
            if date_elem:
                full_text = date_elem.get_text(strip=True)
                match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", full_text)
                if match:
                    publish_date_str = match.group().replace("T", " ")
                else:
                    match = re.search(r"on\s+(.*)", full_text)
                    if match:
                        publish_date_str = match.group(1)

            content_div = soup.select_one(".tjp-single__content") or soup.select_one(
                "article"
            )
            if content_div:
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
            else:
                content = ""

            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    f"JakartaPost date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
                "source": self.base_url,
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
