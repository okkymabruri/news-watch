import logging
import warnings

from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning

from .basescraper import BaseScraper


class RepublikaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.republika.co.id"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        # RSS-first strategy (page ignored).
        return await self.fetch(
            f"{self.base_url}/rss",
            headers={"Accept": "application/xml,*/*", "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )

    def parse_article_links(self, response_text):
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for item in soup.select("item"):
            link_el = item.find("link")
            if not link_el:
                continue

            url = (link_el.get_text(strip=True) or "").strip()
            if not url and link_el.next_sibling:
                url = str(link_el.next_sibling).strip()
            if url:
                links.add(url)

        links = {
            link
            for link in links
            if link.startswith("http") and "republika" in link
        }
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

        # Republika RSS is a general feed; URLs typically don't contain the keyword.
        await self.process_page(links, keyword)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
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

            content_div = soup.select_one(".article-content")
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
                    "Republika date parse failed | url: %s | date: %r",
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
                "source": "republika.co.id",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
