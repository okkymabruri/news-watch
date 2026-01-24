import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class SuaraScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.suara.com"
        self.start_date = start_date
        self.continue_scraping = True
        self._article_href = re.compile(
            r"^https?://www\.suara\.com/.+/20\d{2}/\d{2}/\d{2}/.+"
        )

    async def build_search_url(self, keyword, page):
        url = f"{self.base_url}/search?q={keyword}&page={page}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")

        articles = soup.select("a[href]")
        if not articles:
            return None

        links = {
            a.get("href")
            for a in articles
            if a.get("href")
            and a.get("href").startswith("http")
            and self._article_href.match(a.get("href"))
        }
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                return

            date_el = soup.select_one(".date-article span")
            publish_date_str = date_el.get_text(strip=True) if date_el else ""
            publish_date_str = publish_date_str.strip().strip('"').strip("'")
            publish_date_str = publish_date_str.replace("Jum'at", "Jumat")

            content_el = soup.select_one("article.detail-content")
            if not content_el:
                content_el = soup.select_one("article[class*='detail-content']")
            if not content_el:
                return

            for tag in content_el.select(".kesimpulan"):
                tag.extract()

            content = content_el.get_text(separator=" ", strip=True)
            if not content:
                return

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(
                    "Suara date parse failed | url: %s | date: %r",
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
                "author": "Unknown",
                "content": content,
                "keyword": keyword,
                "category": "Unknown",
                "source": "suara.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
