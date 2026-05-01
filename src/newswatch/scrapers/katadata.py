import json
import logging

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class KatadataScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "katadata.co.id"
        self.api_url = "https://api-search.katadata.co.id/search"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        payload = {
            "q": keyword,
            "source": "katadata",
            "sort": "newest",
            "limit": 10,
            "page": page,
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }

        return await self.fetch(
            self.api_url,
            method="POST",
            data=json.dumps(payload),
            headers=headers,
            timeout=30,
        )

    def parse_article_links(self, response_text):
        try:
            response_json = json.loads(response_text)
        except Exception:
            return None

        articles = response_json.get("results", [])
        if not articles:
            return None

        filtered_hrefs = set()
        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "").lower()
            if url and any(
                keyword.lower() in url.lower() or keyword.lower() in title
                for keyword in self.keywords
            ):
                filtered_hrefs.add(url)

        return filtered_hrefs if filtered_hrefs else None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".section-breadcrumb")
            category = category.get_text(strip=True) if category else ""

            title = soup.select_one(".detail-title.mb-4")
            if title:
                title = title.get_text(strip=True)
            else:
                meta = soup.find("meta", {"property": "og:title"})
                title = meta.get("content", "").strip() if meta else ""

            if not title:
                logging.error(f"Katadata title not found for article {link}")
                return

            author = soup.select_one(".detail-author-name")
            if author:
                author = author.get_text(strip=True).replace("Oleh", "").strip()
            else:
                author = "Unknown"

            publish_date_str = ""
            date_elem = soup.select_one(".detail-date.text-gray")
            if date_elem:
                publish_date_str = date_elem.get_text(strip=True)
            else:
                meta = soup.find("meta", {"property": "article:published_time"})
                publish_date_str = meta.get("content", "") if meta else ""

            content_div = soup.select_one(".detail-main")
            if not content_div:
                content_div = soup.select_one("article")

            if content_div:
                for tag in content_div.find_all("div"):
                    classes = tag.get("class", [])
                    if tag and (
                        any(cls.startswith("widget-baca-juga") for cls in classes)
                        or any("ai-summary" in cls for cls in classes)
                    ):
                        tag.extract()
                content = content_div.get_text(separator="\n", strip=True)
            else:
                content = ""

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(
                    f"Katadata date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
                "source": self.base_url,
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")

    async def build_latest_url(self, page):
        payload = {
            "q": "",
            "source": "katadata",
            "sort": "newest",
            "limit": 10,
            "page": page,
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        return await self.fetch(
            self.api_url,
            method="POST",
            data=json.dumps(payload),
            headers=headers,
            timeout=30,
        )

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        try:
            response_json = json.loads(response_text)
        except Exception:
            return None
        articles = response_json.get("results", [])
        if not articles:
            return None
        filtered_hrefs = set()
        for article in articles:
            url = article.get("url", "")
            if url:
                filtered_hrefs.add(url)
        return filtered_hrefs if filtered_hrefs else None
