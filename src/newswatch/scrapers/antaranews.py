import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class AntaranewsScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.antaranews.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.href_pattern = re.compile(r"https://www\.antaranews\.com/berita/.*")

    async def build_search_url(self, keyword, page):
        # https://www.antaranews.com/search?q=prabowo&page=1
        query_params = {"q": keyword, "page": page}
        url = f"{self.base_url}/search?{urlencode(query_params)}"
        return await self.fetch(url, headers={"User-Agent": "Mozilla/5.0"})

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select(
            ".card__post.card__post-list.card__post__transition.mt-30 a"
        )
        if not articles:
            return None

        filtered_hrefs = list(
            {
                a.get("href")
                for a in articles
                if a.get("href") and self.href_pattern.match(a.get("href"))
            }
        )
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(f"{link}")
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select(".breadcrumbs__item")[1].get_text(strip=True)
            title = soup.select_one(".wrap__article-detail-title").get_text(strip=True)
            author = soup.select_one(".text-muted.mt-2.small").get_text()
            date_items = soup.select(".list-inline-item.mr-2")
            publish_date_str = date_items[-1].get_text(strip=True) if date_items else ""

            content_div = soup.select_one(".wrap__article-detail-content.post-content")

            # loop through paragraphs and remove those with class patterns like "track-*"
            for tag in content_div.find_all(["span", "p"]):
                if "baca-juga" in tag.get("class", []) or "text-muted" in tag.get(
                    "class", []
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
                "source": self.base_url.split("www.")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
