import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class BloombergTechnozScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.bloombergtechnoz.com"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        # https://www.bloombergtechnoz.com/search?query=ekonomi+indonesia&type=berita&pagenum=1
        query_params = {
            "query": keyword,
            "pagenum": page,
        }
        url = f"{self.base_url}/search?{urlencode(query_params)}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select("div.card-box.ft150.margin-bottom-xl a[href]")

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
            category = soup.select_one("ul.sitemap").get_text(" ", strip=True)
            title = soup.select_one(".title.margin-bottom-sm").get_text()

            author = soup.select_one("h5.title.margin-bottom-ss a").get_text(strip=True)
            publish_date_str = soup.select("h5.title.fw4.cl-gray")[0].get_text(
                strip=True
            )

            content_div = soup.select_one(".detail-in")

            next_page_link = soup.select_one(".pager__next")

            # loop through paragraphs and remove those with class patterns like "track-*"
            for tag in content_div.find_all(["div", "span"]):
                if tag and any(
                    cls.startswith("smallbox-pilihan") for cls in tag.get("class", [])
                ):
                    tag.extract()

            if next_page_link:
                # build URL for the next page
                response_text2 = await self.fetch(next_page_link.get("href"))
                if response_text2:
                    soup2 = BeautifulSoup(response_text2, "html.parser")
                    content_div2 = soup2.select_one(".detail-in")
                    content = content_div.get_text(
                        separator=" ", strip=True
                    ) + content_div2.get_text(separator=" ", strip=True)

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