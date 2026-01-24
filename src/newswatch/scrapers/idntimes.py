import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class IDNTimesScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.idntimes.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 20

    async def build_search_url(self, keyword, page):
        url = f"{self.base_url}/search?q={keyword}&page={page}"
        return await self.fetch(url)

    def _extract_flight_payload(self, response_text: str) -> str:
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', response_text)
        return "\n".join(chunks)

    def parse_article_links(self, response_text):
        payload = self._extract_flight_payload(response_text)
        if not payload:
            return None

        # Extract links directly from the escaped flight payload.
        links = set()
        for m in re.finditer(
            r'\\"link\\":\\"(https://www\.idntimes\.com/[^\\"]+)\\"',
            payload,
        ):
            links.add(m.group(1))

        links = {link for link in links if link.startswith("https://www.idntimes.com/")}
        return links or None

    def _extract_total_pages(self, response_text: str) -> int | None:
        payload = self._extract_flight_payload(response_text)
        if not payload:
            return None

        m = re.search(r'\\"meta\\":\{[^}]*\\"total_page\\":(\d+)', payload)
        return int(m.group(1)) if m else None

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

            total_pages = self._extract_total_pages(response_text)
            if total_pages and page >= total_pages:
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

            author_el = soup.select_one("meta[name='author']")
            author = (
                author_el.get("content").strip()
                if author_el and author_el.get("content")
                else "Unknown"
            )

            # Prefer visible date strings (commonly: "15 Jan 2026, 16:24 WIB").
            publish_date_str = ""
            time_el = soup.select_one("time")
            if time_el:
                publish_date_str = time_el.get_text(" ", strip=True)
            if not publish_date_str:
                text = soup.get_text(" ", strip=True)
                m = re.search(
                    r"\\b\\d{1,2}\\s+[A-Za-z]{3}\\s+\\d{4},\\s+\\d{1,2}:\\d{2}\\s+WIB\\b",
                    text,
                )
                publish_date_str = m.group(0) if m else ""

            content_div = soup.select_one("article")
            if not content_div:
                return
            paragraphs = [p.get_text(" ", strip=True) for p in content_div.select("p")]
            paragraphs = [p for p in paragraphs if len(p) > 40]
            content = " ".join(paragraphs).strip()
            if not content:
                return

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(
                    "IDNTimes date parse failed | url: %s | date: %r",
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
                "source": "idntimes.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
