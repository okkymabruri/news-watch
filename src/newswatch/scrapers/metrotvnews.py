import logging
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class MetrotvnewsScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.metrotvnews.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10

        self._headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    async def build_search_url(self, keyword, page):
        # https://www.metrotvnews.com/search?query=ekonomi&page=1
        return await self.fetch(
            f"{self.base_url}/search?query={quote_plus(keyword)}&page={page}",
            headers=self._headers,
            timeout=30,
        )

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select(".item .text h3 a[href]")

        if not articles:
            return None

        links = set()
        for a in articles:
            href = a.get("href")
            if not href:
                continue
            links.add(urljoin(self.base_url, href))

        links = {link for link in links if link.startswith("http")}
        return links or None

    async def fetch_search_results(self, keyword):
        page = 1
        seen_links: set[str] = set()

        while self.continue_scraping and page <= self.max_pages:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break

            filtered_hrefs = self.parse_article_links(response_text)
            if not filtered_hrefs:
                break

            new_links = set(filtered_hrefs) - seen_links
            if not new_links:
                break
            seen_links.update(new_links)

            continue_scraping = await self.process_page(new_links, keyword)
            if not continue_scraping:
                return

            page += 1

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self._headers, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".breadcrumb-content p").get_text(strip=True)
            title = soup.select_one("h1, h2").get_text()

            author_date_str = soup.select_one("p.pt-20.date").get_text(strip=True)
            publish_date_str = author_date_str.split("•")[-1].strip()
            author = author_date_str.split("•")[0].strip()

            content_div = soup.select_one(".news-text")
            if not content_div:
                return

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
            if not content:
                return

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
            logging.error(f"Error parsing article {link}: {e}", exc_info=True)
