import logging

import cloudscraper
from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class JawaposScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.jawapos.com"
        self.start_date = start_date
        self.continue_scraping = True
        # Use cloudscraper for Cloudflare bypass
        self.scraper = cloudscraper.create_scraper()

    async def build_search_url(self, keyword, page):
        # https://www.jawapos.com/search?q=presiden&sort=latest&page=1
        url = f"https://www.jawapos.com/search?q={keyword.replace(' ', '+')}&sort=latest&page={page}"
        # Use cloudscraper synchronously (it handles Cloudflare automatically)
        response = self.scraper.get(url)
        if response.status_code == 200:
            return response.text
        return None

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select("a.latest__link[href]")

        if not articles:
            return None

        filtered_hrefs = {f"{a.get('href')}" for a in articles if a.get("href")}
        return filtered_hrefs

    async def get_article(self, link, keyword):
        # Use cloudscraper for article pages
        response = self.scraper.get(link)
        if response.status_code != 200:
            logging.warning(f"No response for {link}")
            return
        response_text = response.text
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".breadcrumb__wrap").get_text(strip=True)
            title = soup.select_one("h1.read__title").get_text()

            publish_date_str = (
                soup.select_one(".read__info__date")
                .get_text(strip=True)
                .replace("- ", "")
                .replace("| ", "")
            )
            author = soup.select_one(".read__info__author").get_text(strip=True)

            content_div = soup.select_one(".read__content.clearfix")

            # loop through paragraphs and remove those with class patterns like "read__others"
            for tag in content_div.find_all(["strong"]):
                if tag and any(
                    cls.startswith("read__others") for cls in tag.get("class", [])
                ):
                    tag.extract()

            content = content_div.get_text(separator=" ", strip=True)

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    f"JawaPos date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
                "source": self.base_url.split("www.")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}", exc_info=True)
