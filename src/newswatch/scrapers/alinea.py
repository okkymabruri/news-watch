import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class AlineaScraper(BaseScraper):
    """Alinea.id scraper.

    Discovery:
        search: /search?q={keyword}  (server-rendered article cards)
        latest: /indeks              (server-rendered latest listing)
    Article URL pattern: /<section>/<slug>-b<code> where sections are
    peristiwa | politik | bisnis | kolom | gaya-hidup.
    """

    BASE_URL = "https://www.alinea.id"
    SECTIONS = ("peristiwa", "politik", "bisnis", "kolom", "gaya-hidup")
    ARTICLE_RE = re.compile(
        r"^https?://(?:www\.)?alinea\.id/(?:" + "|".join(SECTIONS) + r")/[^/?#]+/?$"
    )

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = self.BASE_URL
        self.start_date = start_date
        self.continue_scraping = True
        self.max_latest_pages = 1
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    async def build_search_url(self, keyword, page):
        query = urlencode({"q": keyword, "page": page})
        return await self.fetch(
            f"{self.BASE_URL}/search?{query}",
            headers=self.headers,
            timeout=30,
        )

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/"):
                href = f"{self.BASE_URL}{href}"
            if not href.startswith("http"):
                continue
            if self.ARTICLE_RE.match(href):
                links.add(href)
        if not links:
            self.continue_scraping = False
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning(f"Alinea no response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")

        try:
            meta_title = soup.find("meta", {"property": "og:title"})
            title = meta_title.get("content", "").strip() if meta_title else ""
            if not title:
                h1 = soup.select_one("h1")
                title = h1.get_text(strip=True) if h1 else ""
            if not title:
                logging.debug(f"Alinea title missing for {link}")
                return

            date_node = soup.select_one("div.frontdate")
            publish_date_str = date_node.get_text(" ", strip=True) if date_node else ""
            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.debug(f"Alinea date parse failed | {link} | {publish_date_str[:60]!r}")
                return

            author = "Unknown"
            reporter = soup.select_one("div.written__reporter div.reporter__nama")
            if reporter:
                author = reporter.get_text(strip=True)

            content_parts = []
            article_node = soup.select_one("article") or soup.select_one("div.artikelend")
            if article_node:
                container = article_node.find_previous("div")
            else:
                container = None
            h1 = soup.select_one("h1")
            anchor = container or (h1.find_parent("div") if h1 else None)
            if anchor:
                for p in anchor.find_all("p"):
                    text = p.get_text(" ", strip=True)
                    if len(text) > 40:
                        content_parts.append(text)
            if not content_parts:
                for p in soup.find_all("p"):
                    text = p.get_text(" ", strip=True)
                    if len(text) > 80:
                        content_parts.append(text)
            content = " ".join(content_parts).strip()
            if not content:
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            path = link.replace(self.BASE_URL, "").strip("/")
            category = path.split("/")[0] if path else "Unknown"

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": self.BASE_URL.split("://", 1)[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Alinea article parse error {link}: {e}")

    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(
            f"{self.BASE_URL}/indeks",
            headers=self.headers,
            timeout=30,
        )

    def parse_latest_article_links(self, response_text):
        return self.parse_article_links(response_text)