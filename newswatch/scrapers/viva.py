import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class VivaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None):
        super().__init__(keywords, concurrency)
        self.base_url = "https://www.viva.co.id"
        self.start_date = start_date
        self.continue_scraping = True
        self.href_pattern = re.compile(r"https://www\.viva\.co\.id/.*/\d+-")

    def build_search_url(self, keyword, page):
        # https://www.viva.co.id/search?q=
        query_params = {"q": keyword}
        return f"{self.base_url}/search?{urlencode(query_params)}"

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select(".article-list-row a")
        if not articles:
            return None

        filtered_hrefs = {
            a.get("href")
            for a in articles
            if a.get("href") and self.href_pattern.match(a.get("href"))
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(f"{link}?page=all")
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            # FIX ME: change to select_one
            category = soup.find(
                "a", {"class": "breadcrumb-step content_center"}
            ).get_text(strip=True)
            title = soup.find("h1", {"class": "main-content-title"}).get_text(
                strip=True
            )
            publish_date_str = soup.find(
                "div", {"class": "main-content-date"}
            ).get_text(strip=True)
            author = soup.find("div", {"class": "main-content-author"}).get_text(
                strip=True
            )

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(f"Error parsing date for article {link}")
                return
            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            content_div = soup.find("div", {"class": "main-content-detail"})
            for elem in content_div.find_all(
                ["div", {"class": ["recommended-article", "widget-other-article"]}]
            ):
                elem.decompose()
            content = content_div.get_text(separator=" ", strip=True)

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
            self.results.append(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
