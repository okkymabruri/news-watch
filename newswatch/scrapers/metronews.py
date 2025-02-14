import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class MetroNewsScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://metrotvnews.com"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        # https://metrotvnews.com/search/ekonomi%20indonesia/0
        return await self.fetch(
            f"https://metrotvnews.com/search/{keyword.replace(' ', '%20')}/{page-1}"
        )

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        # articles = soup.select(".article__link[href]")
        articles = soup.select(".item .text h3 a[href]")

        if not articles:
            return None

        filtered_hrefs = {
            f"{self.base_url}{a.get('href')}" for a in articles if a.get("href")
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".breadcrumb-content p").get_text(strip=True)
            title = soup.select_one("h2").get_text()

            author_date_str = soup.select_one("p.pt-20.date").get_text(strip=True)
            publish_date_str = author_date_str.split("•")[-1].strip()
            author = author_date_str.split("•")[0].strip()

            content_div = soup.select_one(".news-text")

            # # loop through paragraphs and remove those with class patterns like "track-*"
            # for tag in content_div.find_all(["div", "span"]):
            #     # a_tag = tag.find("a", class_=True)
            #     if tag and any(
            #         cls.startswith("inject-baca-juga") or cls.startswith("kompasidRec")
            #         for cls in tag.get("class", [])
            #     ):
            #         tag.extract()
            # remove unwanted elements
            unwanted_phrases = [
                r"Baca juga: ",
            ]
            unwanted_pattern = re.compile("|".join(unwanted_phrases), re.IGNORECASE)

            # Remove unwanted elements from paragraphs, italics, and table cells.
            for tag in content_div.find_all(["td"]):
                tag_text = tag.get_text()
                if unwanted_pattern.search(tag_text):
                    tag.extract()

            content = content_div.get_text(separator=" ", strip=True)

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
                "source": self.base_url.split("https://")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
