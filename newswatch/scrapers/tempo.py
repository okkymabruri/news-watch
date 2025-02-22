import json
import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TempoScraper(BaseScraper):
    def __init__(self, keywords, concurrency=2, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://tempo.co"
        self.api_url = "https://www.tempo.co/api/gateway/articles"
        self.start_date = start_date

    async def build_search_url(self, keyword, page):
        # https://www.tempo.co/api/gateway/articles?status=published&tags%5B%5D=indonesia&limit=10&access=&page=1&page_size=20&order_published_at=DESC
        query_params = {
            "status": "published",
            "tags[]": keyword.replace(" ", "-"),
            "limit": "",
            "access": "",
            "page": page,
            "page_size": "20",
            "order_published_at": "DESC",
        }
        query_string = urlencode(query_params, doseq=True)
        url = f"{self.api_url}?{query_string}"
        return await self.fetch(url, headers={"User-Agent": "Mozilla/5.0"})

    def parse_article_links(self, response_text):
        try:
            response_json = json.loads(response_text)
        except Exception as e:
            logging.error(f"Error decoding JSON response: {e}")
            return None
        articles = response_json.get("data", [])
        filtered_hrefs = {
            f"{self.base_url}/{a['canonical_url']}"
            for a in articles
            if a["canonical_url"]
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers={"User-Agent": "Mozilla/5.0"})
        if not response_text:
            logging.warning(f"No response fetched for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            ld_json_script = soup.find("script", type="application/ld+json")
            if not ld_json_script:
                logging.error("No application/ld+json script found in article page")
                return

            ld_json = json.loads(ld_json_script.string)

            title = ld_json.get("headline", "")
            publish_date_str = ld_json.get("datePublished", "")
            content = ld_json.get("articleBody", "")

            author_field = ld_json.get("author", "")
            if isinstance(author_field, list):
                author = ", ".join([a.get("name", "") for a in author_field])
            else:
                author = ""

            main_entity = ld_json.get("mainEntityOfPage", {})
            category_url = main_entity.get("@id", "")
            category = category_url.split("/")[3] if category_url else ""

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
            logging.error(f"Error parsing article {link}: {e}", exc_info=True)
