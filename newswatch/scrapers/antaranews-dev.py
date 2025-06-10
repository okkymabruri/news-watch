import logging
import re
from datetime import date
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class DetikScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.antaranews.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.href_pattern = re.compile(r".*\.antaranews\.com/.*/d-\d+")

    async def build_search_url(self, keyword, page):
        # https://www.detik.com/search/searchall?query=&page=&result_type=latest&fromdatex=&todatex=
        # https://www.antaranews.com/search?q=prabowo&page=1
        # query_params = {
        #     "query": keyword,
        #     "page": page,
        #     "result_type": "latest",
        #     "fromdatex": self.start_date.strftime("%d/%m/%Y"),
        #     "todatex": date.today().strftime("%d/%m/%Y"),
        # }
        # https://www.antaranews.com/search?q=prabowo&page=1
        url = f"https://www.antaranews.com/search?q={keyword}&page={page}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select(".h5")
        if not articles:
            return None

        filtered_hrefs = {
            a.get("href")
            for a in articles
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(f"{link}?single=1")
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            # category = soup.find("div", class_="page__breadcrumb").find("a").get_text()
            categpory = ""
            title = soup.select_one(".wrap__article-detail-title").get_text(strip=True)
            author = soup.select_one(".detail__author").get_text(strip=True)
            publish_date_str = soup.select_one(".detail__date").get_text(strip=True)

            content_div = soup.find("div", {"class": "detail__body-text"})

            # loop through paragraphs and remove those with class patterns like "track-*"
            for tag in content_div.find_all(["table"]):
                if "linksisip" in tag.get("class", []):
                    tag.extract()

            content = content_div.get_text(separator="\n", strip=True)

            publish_date = self.parse_date(publish_date_str)
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
                "source": self.base_url.split("www.")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
