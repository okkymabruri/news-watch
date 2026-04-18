import json
import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TVRINewsScraper(BaseScraper):
    """
    TVRI News scraper implementation.

    Uses Playwright to extract API credentials from rendered page,
    then queries prod-api.tvrinews.com for true keyword search.
    """

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "tvrinews.com"
        self.api_base = "https://prod-api.tvrinews.com/v1/news"
        self.start_date = start_date
        self.continue_scraping = True
        self._client_id = None
        self._client_secret = None

    async def _get_credentials(self):
        if self._client_id and self._client_secret:
            return self._client_id, self._client_secret

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logging.error(
                "Playwright not installed; install with: playwright install chromium"
            )
            return None, None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            creds = {"client_id": None, "client_secret": None}

            def handle_request(request):
                if "prod-api.tvrinews.com" in request.url:
                    headers = request.headers
                    cid = headers.get("client-id")
                    csec = headers.get("client-secret")
                    if cid and csec:
                        creds["client_id"] = cid
                        creds["client_secret"] = csec

            page.on("request", handle_request)

            try:
                await page.goto("https://www.tvrinews.com/", timeout=15000)
                await page.wait_for_timeout(2000)
            except Exception as e:
                logging.warning(f"TVRI News Playwright navigation failed: {e}")

            page.remove_listener("request", handle_request)
            await browser.close()

        self._client_id = creds.get("client_id")
        self._client_secret = creds.get("client_secret")
        return self._client_id, self._client_secret

    async def build_search_url(self, keyword, page):
        client_id, client_secret = await self._get_credentials()
        if not client_id or not client_secret:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "client-id": client_id,
            "client-secret": client_secret,
            "referer": "https://www.tvrinews.com/",
        }

        # Use main news endpoint with keyword filter
        url = f"{self.api_base}/main?lang=id&q={keyword}&page={page}&limit=20"
        return await self.fetch(url, headers=headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            return None

        items = data.get("data", []) or data.get("items", []) or []
        if not items:
            return None

        filtered_hrefs = set()
        for item in items:
            slug = item.get("slug", "")
            if slug:
                url = f"https://www.{self.base_url}/read/{slug}"
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
            breadcrumb = soup.select_one(".breadcrumb")
            if breadcrumb:
                items = breadcrumb.find_all("a")
                if len(items) > 1:
                    category = items[-1].get_text(strip=True)

            title_elem = soup.select_one("h1") or soup.select_one("title")
            if title_elem:
                title = title_elem.get_text(strip=True)
            else:
                meta = soup.find("meta", {"property": "og:title"})
                title = meta.get("content", "").strip() if meta else ""

            if not title:
                logging.error(f"TVRINews title not found for article {link}")
                return

            author = "Unknown"
            author_elem = soup.select_one(".author")
            if author_elem:
                author = author_elem.get_text(strip=True)

            publish_date_str = ""
            date_elem = soup.select_one(".date") or soup.select_one("time")
            if date_elem:
                publish_date_str = date_elem.get_text(strip=True)

            content_div = soup.select_one(".content") or soup.select_one("article")
            if content_div:
                for tag in content_div.find_all("div"):
                    classes = tag.get("class", [])
                    if tag and any(
                        "related" in cls.lower()
                        or "share" in cls.lower()
                        or "ads" in cls.lower()
                        for cls in classes
                    ):
                        tag.extract()
                content = content_div.get_text(separator=" ", strip=True)
            else:
                content = ""

            if not content:
                return

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(
                    f"TVRINews date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
