import json
import logging
import warnings

from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning

from .basescraper import BaseScraper


class KumparanScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://kumparan.com"
        self.start_date = start_date
        self.continue_scraping = True
        self._sitemap_url = f"{self.base_url}/sitemap_channel_news.xml"

    async def build_search_url(self, keyword, page):
        # Sitemap-first strategy (keyword/page ignored for discovery).
        return await self.fetch(
            self._sitemap_url,
            headers={"Accept": "application/xml,*/*", "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )

    def parse_article_links(self, response_text):
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(response_text, "html.parser")
        links = {loc.get_text(strip=True) for loc in soup.select("url > loc")}
        links = {link for link in links if link.startswith(self.base_url)}
        return links or None

    async def fetch_search_results(self, keyword):
        response_text = await self.build_search_url(keyword, 1)
        if not response_text:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
            return

        links = self.parse_article_links(response_text)
        if not links:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
            return

        kw = keyword.lower().strip()
        filtered = {link for link in links if kw and kw in link.lower()}
        await self.process_page(filtered or links, keyword)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            script = soup.select_one("script[type='application/ld+json']")
            if not script:
                return
            try:
                data = json.loads(script.get_text(strip=True) or "{}")
            except Exception:
                return

            title = (data.get("headline") or "").strip()
            if not title:
                return

            author = "Unknown"
            author_obj = data.get("author")
            if isinstance(author_obj, dict) and author_obj.get("name"):
                author = str(author_obj.get("name")).strip()

            publish_date_str = (data.get("datePublished") or "").strip()
            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    "Kumparan date parse failed | url: %s | date: %r",
                    link,
                    publish_date_str[:50],
                )
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            content = (data.get("articleBody") or "").strip()
            if not content:
                content = title

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": "Unknown",
                "source": "kumparan.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
