import logging
import re

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class KompasScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.kompas.com"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        return await self.fetch(
            f"https://search.kompas.com/search?q={keyword}&sort=latest&page={page}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
            },
        )

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")

        # Check for "no results" message
        if (
            "tidak ditemukan" in response_text
            or "Coba kata kunci lain" in response_text
        ):
            return None

        articles = soup.select(".article-link[href]")
        if not articles:
            return None

        filtered_hrefs = {
            a.get("href")
            for a in articles
            if a.get("href") and "video.kompas.com" not in a.get("href")
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(
            f"{link}?page=all",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
            },
        )
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".breadcrumb__wrap").get_text(
                separator="/", strip=True
            )
            title = soup.select_one(".read__title").get_text(strip=True)
            time_text = soup.select_one(".read__time").get_text(strip=True)
            publish_date_str = time_text
            if "-" in time_text:
                parts = time_text.split("- ", 1)
                if len(parts) == 2:
                    publish_date_str = parts[1]
            if "Diperbarui" in publish_date_str:
                publish_date_str = publish_date_str.split("Diperbarui")[1].strip()

            # Normalize common Kompas prefix so dateparser can parse it.
            publish_date_str = re.sub(r"^Kompas\.com\s*,\s*", "", publish_date_str)
            author = soup.select_one(".credit-title-name").get_text(strip=True)

            content_div = soup.select_one(".read__content")

            # loop through paragraphs and remove those with class patterns like "track-*"
            for tag in content_div.find_all(["div", "span"]):
                # a_tag = tag.find("a", class_=True)
                if tag and any(
                    cls.startswith("inject-baca-juga") or cls.startswith("kompasidRec")
                    for cls in tag.get("class", [])
                ):
                    tag.extract()
            # remove unwanted elements
            unwanted_phrases = [
                r"Simak.*WhatsApp Channel",
                r"https://www\.whatsapp\.com/channel/",
                r"Baca juga: ",
            ]
            unwanted_pattern = re.compile("|".join(unwanted_phrases), re.IGNORECASE)

            for tag in content_div.find_all(["i", "p"]):
                tag_text = tag.get_text()
                if unwanted_pattern.search(tag_text):
                    tag.extract()

            content = content_div.get_text(separator=" ", strip=True)

            if not content:
                return

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                publish_date = self.parse_date(
                    publish_date_str,
                    languages=["id"],
                    settings={"PREFER_DAY_OF_MONTH": "first"},
                )
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
