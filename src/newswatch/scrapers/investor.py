"""
Investor.id scraper — uses /search/{keyword} endpoint for true keyword search.
"""

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class InvestorScraper(BaseScraper):
    """
    Investor.id scraper implementation.

    Uses /search/{keyword} endpoint for keyword search.
    Pagination: /search/{keyword}/2, /search/{keyword}/3, ...
    """

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "investor.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    async def build_search_url(self, keyword, page):
        if page == 1:
            url = f"https://www.{self.base_url}/search/{quote(keyword.lower())}"
        else:
            url = f"https://www.{self.base_url}/search/{quote(keyword.lower())}/{page}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")

        # Detect no-result page: Investor shows "Halaman yang Anda tuju tidak ditemukan"
        # when the search keyword has no matching articles, but still renders sidebar/trending links.
        if "halaman yang anda tuju tidak ditemukan" in response_text.lower():
            self.continue_scraping = False
            return None

        pattern = re.compile(
            r"^/(market|berita|ekonomi|nasional|sosial|teknologi)/\d+/"
        )
        filtered_hrefs = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if pattern.search(href):
                if not href.startswith("http"):
                    href = f"https://www.{self.base_url}{href}"
                filtered_hrefs.add(href)

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

            title_elem = soup.select_one("h1")
            if not title_elem:
                meta = soup.find("meta", {"property": "og:title"})
                title = meta.get("content", "").strip() if meta else ""
            else:
                title = title_elem.get_text(strip=True)

            if not title:
                logging.error(f"Investor title not found for article {link}")
                return

            author = "Unknown"
            author_line = soup.select_one(".col.small.pt-1")
            if author_line:
                text = author_line.get_text(strip=True)
                if "Penulis" in text:
                    author = text.split("Penulis")[-1].strip().lstrip(":").strip()

            publish_date_str = ""
            date_span = soup.select_one("span.text-muted")
            if date_span:
                publish_date_str = date_span.get_text(strip=True)

            content_div = soup.select_one(".body-content")
            if not content_div:
                content_div = soup.select_one("article")
            if not content_div:
                return

            for tag in content_div.find_all("div"):
                classes = tag.get("class", [])
                if tag and any(
                    cls.startswith("id-group")
                    or cls.startswith("baca-juga")
                    or cls.startswith("related")
                    or "ads" in cls.lower()
                    or "outstream" in cls.lower()
                    for cls in classes
                ):
                    tag.extract()
            content = content_div.get_text(separator=" ", strip=True)

            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    f"Investor date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
