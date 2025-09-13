import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class OkezoneScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.okezone.com"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        # https://search.okezone.com/loaddata/article/ekonomi/1
        url = f"https://search.okezone.com/loaddata/article/{keyword}/{page}"

        return await self.fetch(
            url,
            headers={"user-agent": "Mozilla/5.0"},
        )

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select("a[href*='/read/']")
        if not articles:
            return None

        filtered_hrefs = {
            a.get("href")
            for a in articles
            if a.get("href") and a.get("href").startswith("http")
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            breadcrumb = soup.select(".breadcrumb a")
            category = breadcrumb[-1].get_text(strip=True) if breadcrumb else "Unknown"

            title_elem = soup.select_one(".title-article h1")
            if not title_elem:
                return
            title = title_elem.get_text(strip=True)
            
            author_elem = soup.select_one(".journalist a[title]")
            author = author_elem.get("title") if author_elem else "Unknown"
            
            date_elem = soup.select_one(".journalist span")
            if not date_elem:
                return
            publish_date_str = (
                date_elem.get_text(strip=True)
                .split("Jurnalis-")[1]
                .strip()
                .replace("|", "")
                .replace("'", "")
            )

            content_div = soup.select_one(".c-detail.read")

            # remove unwanted elements
            for tag in content_div.find_all(["div", "span"]):
                if tag and any(
                    cls.startswith("inject-") or cls.startswith("banner")
                    for cls in tag.get("class", [])
                ):
                    tag.extract()

            # remove unwanted text patterns
            unwanted_phrases = [
                r"Baca juga:",
                r"Follow.*WhatsApp Channel",
                r"Telusuri berita.*lainnya",
            ]
            unwanted_pattern = re.compile("|".join(unwanted_phrases), re.IGNORECASE)

            for tag in content_div.find_all(["p", "div"]):
                tag_text = tag.get_text()
                if unwanted_pattern.search(tag_text):
                    tag.extract()

            content = content_div.get_text(separator=" ", strip=True)

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(f"Okezone date parse failed | url: {link} | date: {repr(publish_date_str[:50])}")
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
                "source": "okezone.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception:
            pass
