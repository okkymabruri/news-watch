import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class Liputan6Scraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.liputan6.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_href = re.compile(r"^https?://www\.liputan6\.com/.+/read/\d+/?.*")

        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def build_search_url(self, keyword, page):
        # Liputan6 `/search` results are not paginated via `page=` in HTML (page 1 == page 2).
        # Use tag pages for paging when keyword is a single token; otherwise fall back to search.
        if " " not in keyword.strip():
            query = urlencode({"page": page})
            url = f"{self.base_url}/tag/{keyword.strip().lower()}?{query}"
        else:
            query = urlencode({"q": keyword})
            url = f"{self.base_url}/search?{query}"
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")

        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            if href.startswith("/"):
                href = f"{self.base_url}{href}"

            href = href.split("#")[0]
            if not self._article_href.search(href):
                continue

            # Skip photo pages (usually low text density)
            if "/photo/" in href:
                continue

            links.add(href)

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
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                return

            publish_date_str = ""
            meta_time = soup.select_one("meta[property='article:published_time']")
            if meta_time and meta_time.get("content"):
                publish_date_str = meta_time.get("content")

            author = "Unknown"
            meta_author = soup.select_one("meta[name='author']")
            if meta_author and meta_author.get("content"):
                author = meta_author.get("content").strip() or author

            category = "Unknown"
            meta_section = soup.select_one("meta[property='article:section']")
            if meta_section and meta_section.get("content"):
                category = meta_section.get("content").strip() or category

            content_root = (
                soup.select_one("div.article-content-body")
                or soup.select_one("div.article-content-body__item-content")
                or soup.select_one("article")
            )
            if not content_root:
                return

            for tag in content_root.find_all(["script", "style"]):
                tag.extract()

            # Prefer paragraph text to avoid unrelated UI text
            paragraphs = [
                p.get_text(" ", strip=True) for p in content_root.find_all("p")
            ]
            paragraphs = [p for p in paragraphs if p]
            content = "\n".join(paragraphs).strip() if paragraphs else ""
            if not content:
                content = content_root.get_text(separator="\n", strip=True)

            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    "Liputan6 date parse failed | url: %s | date: %r",
                    link,
                    publish_date_str[:50],
                )
                return

            if self.start_date and publish_date < self.start_date:
                return

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "liputan6.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
