import logging
import re
from datetime import date
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class KatadataScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://katadata.co.id"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        # https://katadata.co.id/search/news/ihsg%2520merah/-/-/-/-/-/-/10
        url = f"{self.base_url}/search/news/{keyword.replace(' ', '%2520')}/-/-/-/-/-/-/{(page-1)*10}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        # articles = soup.select(".article article--berita d-flex  .media__link")
        articles = soup.select(
            "article.article.article--berita.d-flex div.content-text > a[href]"
        )

        if not articles:
            return None

        filtered_hrefs = {a.get("href") for a in articles if a.get("href")}
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".section-breadcrumb").get_text(strip=True)
            title = soup.select_one(".detail-title.mb-4").get_text(strip=True)
            author = (
                soup.select_one(".detail-author-name")
                .get_text(strip=True)
                .replace("Oleh", "")
            )
            publish_date_str = soup.select_one(".detail-date.text-gray").get_text(
                strip=True
            )

            # content_div = soup.find_all("div", class_ = "detail-main")
            content_div = soup.select_one(".detail-main")

            # loop through paragraphs and remove those with class patterns "widget-baca-juga*" or if any class contains "ai-summary"
            for tag in content_div.find_all("div"):
                classes = tag.get("class", [])
                if tag and (
                    any(cls.startswith("widget-baca-juga") for cls in classes)
                    or any("ai-summary" in cls for cls in classes)
                ):
                    tag.extract()

            content = content_div.get_text(separator="\n", strip=True)

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
