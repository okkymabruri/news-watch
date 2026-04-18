import json
import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TempoScraper(BaseScraper):
    def __init__(self, keywords, concurrency=1, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.tempo.co"
        self.algolia_url = "https://u2ciazrcad-2.algolianet.com/1/indexes/production_articles/query"
        self.start_date = start_date
        self.max_pages = 10

    async def build_search_url(self, keyword, page):
        params = {"x-algolia-agent": "Algolia for JavaScript (4.24.0); Browser"}
        query_string = urlencode(params)
        url = f"{self.algolia_url}?{query_string}"
        body = {
            "query": keyword,
            "filters": "NOT unpublished_at",
            "hitsPerPage": 20,
            "page": page - 1,
        }
        return await self.fetch(
            url,
            method="POST",
            data=json.dumps(body),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "x-algolia-api-key": "a74cdcfcc2c69b5dabb4d13c4ce52788",
                "x-algolia-application-id": "U2CIAZRCAD",
                "Referer": "https://www.tempo.co/",
            },
            timeout=45,
        )

    def parse_article_links(self, response_text):
        try:
            response_json = json.loads(response_text)
        except Exception as e:
            logging.error(f"Error decoding JSON response: {e}")
            return None
        hits = response_json.get("hits", [])
        if not hits:
            return None
        filtered_hrefs = set()
        for hit in hits:
            url = hit.get("canonical_url", "")
            if url:
                if not url.startswith("http"):
                    url = f"{self.base_url}/{url}"
                filtered_hrefs.add(url)
        return filtered_hrefs or None

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
        response_text = await self.fetch(
            link, headers={"User-Agent": "Mozilla/5.0"}, timeout=45
        )
        if not response_text:
            logging.warning(f"No response fetched for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            title = ""
            for h in soup.select("h1"):
                t = h.get_text(" ", strip=True)
                if t:
                    title = t
                    break
            if not title:
                og_title = soup.select_one("meta[property='og:title']")
                if og_title and og_title.get("content"):
                    title = og_title.get("content").strip()
            if not title:
                return

            author_el = soup.select_one("meta[name='author']")
            author = (
                author_el.get("content").strip()
                if author_el and author_el.get("content")
                else "Unknown"
            )

            date_el = soup.select_one("meta[property='article:published_time']")
            publish_date_str = (
                date_el.get("content").strip()
                if date_el and date_el.get("content")
                else ""
            )

            content_div = soup.select_one(".detail-content")
            if not content_div:
                content_div = soup.select_one("article")
            if not content_div:
                return

            paragraphs = [p.get_text(" ", strip=True) for p in content_div.select("p")]
            paragraphs = [p for p in paragraphs if len(p) > 40]
            content = " ".join(paragraphs).strip()
            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    "Tempo date parse failed | url: %s | date: %r",
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
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": "Unknown",
                "source": "tempo.co",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
