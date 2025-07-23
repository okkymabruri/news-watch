import logging
import re
from datetime import date
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class DetikScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.detik.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.href_pattern = re.compile(r".*\.detik\.com/.*/d-\d+")

    async def build_search_url(self, keyword, page):
        # https://www.detik.com/search/searchall?query=&page=&result_type=latest&fromdatex=&todatex=
        query_params = {
            "query": keyword,
            "page": page,
            "result_type": "latest",
            "fromdatex": self.start_date.strftime("%d/%m/%Y"),
            "todatex": date.today().strftime("%d/%m/%Y"),
        }

        url = f"{self.base_url}/search/searchnews?{urlencode(query_params)}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select(".list-content__item .media__link")
        if not articles:
            return None

        filtered_hrefs = {
            a.get("href")
            for a in articles
            if a.get("href")
            and self.href_pattern.match(a.get("href"))
            and "wolipop.detik.com" not in a.get("href")
            and "/detiktv/" not in a.get("href")
            and "/pop/" not in a.get("href")
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(f"{link}?single=1")
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.find("div", class_="page__breadcrumb").find("a").get_text()
            title = soup.select_one(".detail__title").get_text(strip=True)
            # Try regular article author first, then column author
            author_elem = soup.select_one(".detail__author")
            if not author_elem:
                author_elem = soup.select_one(".box-kolumnis h5")
            author = author_elem.get_text(strip=True) if author_elem else "Unknown"
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
