import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class MediaIndonesiaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://mediaindonesia.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.href_pattern = re.compile(r"https://mediaindonesia\.com/.*/\d+/")

    async def build_search_url(self, keyword, page):
        url = f"{self.base_url}/search"
        if page == 1:
            payload = {"q": keyword}
        else:
            payload = {"q": keyword, "next": str(page - 1)}

        return await self.fetch(url, method="POST", data=payload)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select("ul.list-3 div.text a[href]")
        if not articles:
            return None

        filtered_hrefs = {
            a.get("href")
            for a in articles
            if a.get("href") and self.href_pattern.match(a.get("href"))
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".mi-breadcrumb").get_text()

            title = soup.select_one("h1").get_text(strip=True)
            author = soup.select_one(".author-2").get_text(strip=True)
            publish_date_str = soup.select_one(".datetime").get_text(strip=True)

            content_div = soup.select_one("div.article")

            # remove unwanted elements
            for elem in content_div.select(
                "p.related-news, .flying-carpet, .ext-channel, .info-author, ._ap_apex_ad, script, .dfp-ad"
            ):
                elem.decompose()

            content = content_div.get_text(separator=" ", strip=True)

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(f"Error parsing date for article {link}")
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
                "source": self.base_url.split("://")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
