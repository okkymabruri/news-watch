import logging
from urllib.parse import urlencode, unquote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class BisnisScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "bisnis.com"
        self.start_date = start_date

    async def build_search_url(self, keyword, page):
        # https://search.bisnis.com/?q=prabowo&page=2
        query_params = {
            "q": keyword,
            "page": page,
        }
        url = f"https://search.{self.base_url}/?{urlencode(query_params)}"
        # Use shorter timeout for search pages - 15 seconds
        return await self.fetch(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.find_all("a", class_="artLink artLinkImg")
        if not articles:
            return None

        filtered_hrefs = {
            unquote(a["href"].split("link?url=")[1])
            for a in articles
            if a["href"]
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        # Use shorter timeout for article pages - 10 seconds
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")

        try:
            breadcrumb = soup.select_one(".breadcrumb")
            breadcrumb_items = breadcrumb.select(".breadcrumbItem") if breadcrumb else []
            
            category_parts = []
            for item in breadcrumb_items:
                if "Home" not in item.get_text(strip=True):
                    link_text = item.select_one(".breadcrumbLink")
                    if link_text:
                        category_parts.append(link_text.get_text(strip=True))
            
            category = " - ".join(category_parts) if category_parts else ""
            
            title = soup.select_one("h1.detailsTitleCaption").get_text()

            publish_date_str = (
                soup.select_one(".detailsAttributeDates")
                .get_text(strip=True)
            )
            author = soup.select_one(".authorName").get_text(strip=True).split("-")[0]

            content_div = soup.select_one("article.detailsContent.force-17.mt40")

            # loop through paragraphs and remove those with class patterns like "read__others"
            for tag in content_div.find_all(["div"]):
                if tag and any(
                    cls.startswith("baca-juga-box") for cls in tag.get("class", [])
                ):
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
                "source": self.base_url,
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
