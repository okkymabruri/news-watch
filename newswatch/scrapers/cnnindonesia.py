import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class CNNIndonesiaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.cnnindonesia.com"
        self.api_url = f"{self.base_url}/api/v3/search"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_href = re.compile(
            r"^https?://www\.cnnindonesia\.com/.+/\d{14}-\d+-\d+/"
        )

        self.api_headers = {
            "Accept": "application/json,*/*",
            "Referer": f"{self.base_url}/search?query=",
        }

    async def build_search_url(self, keyword, page):
        # Use the site's internal search API.
        # Paging uses `start` offset (0-based).
        limit = 20
        start = (page - 1) * limit

        query_params = {
            "query": keyword,
            "start": start,
            "limit": limit,
        }
        url = f"{self.api_url}?{urlencode(query_params)}"
        return await self.fetch(url, headers=self.api_headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        try:
            data = __import__("json").loads(response_text)
        except Exception:
            return None

        articles = data.get("data") or []
        if not articles:
            return None

        links = set()
        for a in articles:
            url = a.get("url")
            if not url:
                continue
            if self._article_href.search(url):
                links.add(url)

        return links if links else None

    async def fetch_search_results(self, keyword):
        page = 1
        found_articles = False

        while self.continue_scraping and page <= self.max_pages:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break

            filtered_hrefs = self.parse_article_links(response_text)
            if not filtered_hrefs:
                break

            found_articles = True
            continue_scraping = await self.process_page(filtered_hrefs, keyword)
            if not continue_scraping:
                break

            page += 1

        if not found_articles:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                og_title = soup.select_one("meta[property='og:title']")
                if og_title and og_title.get("content"):
                    title = og_title.get("content").strip()
            if not title:
                return

            category = "ekonomi"
            breadcrumb = soup.select_one(".breadcrumb")
            if breadcrumb:
                category = breadcrumb.get_text(separator="/", strip=True) or category

            publish_date_str = ""
            meta_publish = soup.select_one("meta[name='publishdate']")
            if meta_publish and meta_publish.get("content"):
                publish_date_str = meta_publish.get("content")
            else:
                meta_time = soup.select_one("meta[property='article:published_time']")
                if meta_time and meta_time.get("content"):
                    publish_date_str = meta_time.get("content")

            content_div = soup.select_one(".detail-text")

            if not content_div:
                # Some CNNIndonesia pages (e.g. video short updates) don't have `.detail-text`.
                # Fall back to the most content-rich `div` with class containing `detail`.
                best_div = None
                best_len = 0
                for div in soup.select("div[class*='detail']"):
                    # Prefer containers that actually look like article bodies
                    if len(div.find_all("p")) < 2:
                        continue
                    text_len = len(div.get_text(" ", strip=True))
                    if text_len > best_len:
                        best_len = text_len
                        best_div = div
                content_div = best_div

            content = (
                content_div.get_text(separator="\n", strip=True) if content_div else ""
            )
            if not content:
                return

            # Remove common share/clipboard noise
            content = "\n".join(
                line
                for line in content.splitlines()
                if line.strip()
                and line.strip().lower() not in {"bagikan:", "url telah tercopy"}
            ).strip()
            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    "CNNIndonesia date parse failed | url: %s | date: %r",
                    link,
                    publish_date_str[:50],
                )
                return
            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": "Unknown",
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "cnnindonesia.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
