import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class CNBCScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.cnbcindonesia.com"
        self.start_date = start_date
        self.max_pages = 10

    async def build_search_url(self, keyword, page):
        # https://www.cnbcindonesia.com/search?query=&fromdate=&page=
        query_params = {
            "query": keyword,
            "fromdate": self.start_date.strftime("%Y/%m/%d"),
            "page": page,
        }
        url = f"{self.base_url}/search?{urlencode(query_params)}"
        return await self.fetch(url)

    async def _fetch_rss_links(self, keyword):
        """Legacy — returns only links (used by existing code paths)."""
        items = await self._fetch_rss_items(keyword)
        if not items:
            return None
        return {link for link, _ in items}

    async def _fetch_rss_items(self, keyword):
        """Fetch RSS and return (link, title) pairs for keyword filtering."""
        rss_url = f"{self.base_url}/rss?{urlencode({'tag': keyword})}"
        rss_text = await self.fetch(
            rss_url,
            headers={"Accept": "application/xml,*/*", "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        if not rss_text:
            return None

        soup = BeautifulSoup(rss_text, "xml")
        items = []
        for item in soup.select("item"):
            link_el = item.find("link")
            title_el = item.find("title")
            if not link_el or not title_el:
                continue
            link = link_el.get_text(strip=True)
            title = title_el.get_text(strip=True)
            if not link.startswith("http"):
                continue
            # Filter non-article URLs (e.g. homepage, video pages)
            article_href = re.compile(
                r"^https?://www\.cnbcindonesia\.com/.+?/\d+-\d+-\d+/"
            )
            if article_href.search(link):
                items.append((link, title))

        return items or None

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select(".nhl-list a.group[href]")
        if not articles:
            return None

        filtered_hrefs = {a.get("href") for a in articles if a.get("href")}
        return filtered_hrefs

    async def fetch_search_results(self, keyword):
        # Prefer HTML search (richer + supports date filter), but fall back to RSS when blocked.
        page = 1
        while self.continue_scraping and page <= self.max_pages:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break

            filtered_hrefs = self.parse_article_links(response_text)
            if not filtered_hrefs:
                break

            continue_scraping = await self.process_page(filtered_hrefs, keyword)
            if not continue_scraping:
                return

            page += 1

        rss_links = await self._fetch_rss_links(keyword)
        if not rss_links:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
            return

        # RSS returns general feed — enforce strict-search: filter
        # articles whose title or URL contains the keyword.
        # Extract (link, title) pairs from RSS for efficient pre-filtering.
        kw = keyword.lower().strip()
        rss_items = await self._fetch_rss_items(keyword)
        if not rss_items:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
            return

        # Pre-filter by keyword in URL or title
        filtered = {
            link for link, title in rss_items
            if kw in link.lower() or kw in title.lower()
        }
        if not filtered:
            return

        await self.process_page(filtered, keyword)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")

        try:
            category = soup.select_one("a.text-xs.font-semibold[href='#']").get_text(
                strip=True
            )
            title = soup.select_one("h1.mb-4.text-32.font-extrabold").get_text(
                strip=True
            )
            author = soup.select("div.mb-1.text-base.font-semibold")[1].get_text(
                strip=True
            )
            publish_date_str = soup.select_one("div.text-cm.text-gray").get_text(
                strip=True
            )

            content_div = soup.find("div", {"class": "detail-text"})

            # loop through paragraphs and remove those with class patterns like "sisip-*"
            for tag in content_div.find_all(["table", "div"]):
                class_list = tag.get("class", [])
                if any(
                    cls.startswith("sisip_") or cls.startswith("link_sisip")
                    for cls in class_list
                ):
                    tag.extract()

            content = content_div.get_text(separator="\n", strip=True)

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
                "source": self.base_url.split("www.")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
