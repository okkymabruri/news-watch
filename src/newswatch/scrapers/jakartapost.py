import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class JakartaPostScraper(BaseScraper):
    """
    The Jakarta Post scraper implementation.

    Uses /latest and /business index pages since
    native search requires JavaScript rendering.
    """

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "thejakartapost.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    async def build_search_url(self, keyword, page):
        if page == 1:
            url = f"https://www.{self.base_url}/latest"
        elif page == 2:
            url = f"https://www.{self.base_url}/business"
        else:
            self.continue_scraping = False
            return None
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        pattern = re.compile(r"thejakartapost\.com/.*\.html$")
        filtered_hrefs = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = f"https://www.{self.base_url}{href}"
            if pattern.search(href):
                filtered_hrefs.add(href)

        return filtered_hrefs if filtered_hrefs else None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")

        try:
            category = ""
            breadcrumb = soup.select_one(".tjp-single__head")
            if breadcrumb:
                items = breadcrumb.find_all("a")
                categories = [
                    item.get_text(strip=True)
                    for item in items
                    if item.get_text(strip=True)
                ]
                if categories:
                    category = " / ".join(categories[:2])

            title_elem = soup.select_one(".tjp-single__head h1")
            if not title_elem:
                meta = soup.find("meta", {"property": "og:title"})
                title = meta.get("content", "").strip() if meta else ""
            else:
                title = title_elem.get_text(strip=True)

            if not title:
                logging.error(f"JakartaPost title not found for article {link}")
                return

            author = "Unknown"
            author_elem = soup.select_one(".tjp-single__head .author")
            if author_elem:
                author = author_elem.get_text(strip=True)

            publish_date_str = ""
            date_elem = soup.select_one(".tjp-single__head .created")
            if date_elem:
                full_text = date_elem.get_text(strip=True)
                match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", full_text)
                if match:
                    publish_date_str = match.group().replace("T", " ")
                else:
                    match = re.search(r"on\s+(.*)", full_text)
                    if match:
                        publish_date_str = match.group(1)

            content_div = soup.select_one(".tjp-single__content")
            if content_div:
                for tag in content_div.find_all(["div", "script", "style"]):
                    classes = tag.get("class", [])
                    if tag and any(
                        "ad" in cls.lower()
                        or "related" in cls.lower()
                        or "popular" in cls.lower()
                        or "newsletter" in cls.lower()
                        for cls in classes
                    ):
                        tag.extract()
                content = content_div.get_text(separator=" ", strip=True)
            else:
                content = ""

            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    f"JakartaPost date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
