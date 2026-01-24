import logging

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class MerdekaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.merdeka.com"
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
            if link.startswith(self.base_url) and link.endswith(".html")
        }

        if not links:
            return None

        return links

    async def fetch_search_results(self, keyword):
        # Only one RSS fetch per keyword.
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

            date_el = soup.select_one("meta[property='article:published_time']")
            publish_date_str = (
                date_el.get("content").strip()
                if date_el and date_el.get("content")
                else ""
            )

            content_div = soup.select_one("article")
            chunk = content_div if content_div else soup

            paragraphs = []
            for p in chunk.select("p"):
                text = p.get_text(" ", strip=True)
                if len(text) < 80:
                    continue
                if any(
                    bad in text
                    for bad in [
                        "ADVERTISEMENT",
                        "insertAdjacentElement",
                        "window.",
                    ]
                ):
                    continue
                paragraphs.append(text)

            content = " ".join(paragraphs).strip()
            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    "Merdeka date parse failed | url: %s | date: %r",
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
                "source": "merdeka.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
