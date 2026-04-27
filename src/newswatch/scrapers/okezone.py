"""
Okezone scraper — uses /tag/{keyword} endpoint for keyword search.

The search.okezone.com endpoint is unreliable; tag pages return
query-specific articles with a detectable no-result state.
"""

import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class OkezoneScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.okezone.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    async def build_search_url(self, keyword, page):
        url = f"{self.base_url}/tag/{keyword.lower()}"
        if page > 1:
            url += f"/{page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")

        # Detect no-result page: title is generic homepage title
        title_el = soup.find("title")
        if title_el:
            title = title_el.get_text(strip=True)
            if "Berita Terkini dan Informasi Terbaru" in title:
                self.continue_scraping = False
                return None

        pattern = re.compile(r"https?://[\w.-]*okezone\.com/read/\d+/\d+/\d+/\d+/")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"
            if pattern.match(href):
                links.add(href)

        return links if links else None

    async def fetch_search_results(self, keyword):
        """Fetch search results with pagination limit."""
        page = 1
        found_articles = False

        while self.continue_scraping and page <= self.max_pages:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break

            filtered_hrefs = self.parse_article_links(response_text)
            if not filtered_hrefs:
                break

            found_articles = True
            continue_scraping = await self.process_page(filtered_hrefs, keyword)
            if not continue_scraping:
                break

            page += 1

        if not found_articles:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            breadcrumb = soup.select(".breadcrumb a")
            category = breadcrumb[-1].get_text(strip=True) if breadcrumb else "Unknown"

            title_elem = soup.select_one(".title-article h1")
            if not title_elem:
                title_elem = soup.select_one("h1")
            if not title_elem:
                return
            title = title_elem.get_text(strip=True)

            author_elem = soup.select_one(".journalist a[title]")
            author = author_elem.get("title") if author_elem else "Unknown"

            date_elem = soup.select_one(".journalist span")
            if not date_elem:
                return
            publish_date_str = (
                date_elem.get_text(strip=True)
                .split("Jurnalis-")[1]
                .strip()
                .replace("|", "")
                .replace("'", "")
            )

            content_div = soup.select_one(".c-detail.read")
            if not content_div:
                content_div = soup.select_one("article")
            if not content_div:
                return

            for tag in content_div.find_all(["div", "span"]):
                if tag and any(
                    cls.startswith("inject-") or cls.startswith("banner")
                    for cls in tag.get("class", [])
                ):
                    tag.extract()

            unwanted_phrases = [r"Baca juga:", r"Follow.*WhatsApp Channel", r"Telusuri berita.*lainnya"]
            unwanted_pattern = re.compile("|".join(unwanted_phrases), re.IGNORECASE)
            for tag in content_div.find_all(["p", "div"]):
                tag_text = tag.get_text()
                if unwanted_pattern.search(tag_text):
                    tag.extract()

            content = content_div.get_text(separator=" ", strip=True)
            if not content:
                return

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(
                    "Okezone date parse failed | url: %s | date: %r",
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
                "source": "okezone.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")

    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(self.base_url, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        pattern = re.compile(r"https?://[\w.-]*okezone\.com/read/\d+/\d+/\d+/\d+/")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"
            if pattern.match(href):
                links.add(href)
        return links or None
