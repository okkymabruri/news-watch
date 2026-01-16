import logging
from urllib.parse import unquote, urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class BisnisScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "bisnis.com"
        self.start_date = start_date

    async def build_search_url(self, keyword, page):
        # https://search.bisnis.com/?q=prabowo&page=2
        query_params = {
            "q": keyword,
            "page": page,
        }
        url = f"https://search.{self.base_url}/?{urlencode(query_params)}"
        # Use shorter timeout for search pages - 15 seconds
        return await self.fetch(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.find_all("a", class_="artLink artLinkImg")
        if not articles:
            return None

        filtered_hrefs = {
            unquote(a["href"].split("link?url=")[1]) for a in articles if a["href"]
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        # Use shorter timeout for article pages - 10 seconds
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")

        try:
            breadcrumb = soup.select_one(".breadcrumb")
            breadcrumb_items = (
                breadcrumb.select(".breadcrumbItem") if breadcrumb else []
            )

            category_parts = []
            for item in breadcrumb_items:
                if "Home" not in item.get_text(strip=True):
                    link_text = item.select_one(".breadcrumbLink")
                    if link_text:
                        category_parts.append(link_text.get_text(strip=True))

            category = " - ".join(category_parts) if category_parts else ""

            title_elem = soup.select_one("h1.detailsTitleCaption") or soup.select_one(
                "h1"
            )
            if not title_elem:
                logging.error(f"Title not found for article {link}")
                return
            title = title_elem.get_text()

            # Try multiple date selectors based on bisnis.com subdomain
            date_elem = soup.select_one(".detailsAttributeDates")  # regular bisnis.com
            if date_elem:
                publish_date_str = date_elem.get_text(strip=True)
            else:
                date_elem = soup.select_one(".authorTime")  # premium.bisnis.com
                if date_elem:
                    publish_date_str = date_elem.get_text(strip=True)
                else:
                    # koran.bisnis.com - date is in .author div after <br>
                    author_div = soup.select_one(".author")
                    if author_div:
                        import re

                        full_text = author_div.get_text(separator="|", strip=True)
                        # Extract date pattern: DD/MM/YYYY HH:MM WIB
                        date_match = re.search(
                            r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+\w+", full_text
                        )
                        if date_match:
                            # Also get the day name if present (e.g., "Kamis")
                            parts = full_text.split("|")
                            if len(parts) > 1:
                                publish_date_str = parts[
                                    -1
                                ].strip()  # Get the last part after the separator
                            else:
                                publish_date_str = date_match.group()
                        else:
                            publish_date_str = ""
                    else:
                        meta_date = soup.find(
                            "meta", {"property": "article:published_time"}
                        )
                        publish_date_str = (
                            meta_date.get("content", "") if meta_date else ""
                        )

            # Try multiple author selectors based on bisnis.com subdomain
            author_elem = soup.select_one(".authorName") or soup.select_one(
                ".authorNames"
            )
            if author_elem:
                author = author_elem.get_text(strip=True).split("-")[0]
            else:
                # koran.bisnis.com - author is in .author div before <br>
                author_div = soup.select_one(".author")
                if author_div:
                    full_text = author_div.get_text(separator="|", strip=True)
                    parts = full_text.split("|")
                    if parts:
                        # First part is the author name (before the date)
                        author = parts[0].strip()
                    else:
                        author = "Unknown"
                else:
                    author = "Unknown"

            content_div = soup.select_one("article.detailsContent.force-17.mt40")
            if not content_div:
                content_div = soup.select_one("article.detailsContent")
            if not content_div:
                content_div = soup.select_one(".detailsContent")

            if content_div:
                # loop through paragraphs and remove those with class patterns like "read__others"
                for tag in content_div.find_all(["div"]):
                    if tag and any(
                        cls.startswith("baca-juga-box") for cls in tag.get("class", [])
                    ):
                        tag.extract()
                content = content_div.get_text(separator=" ", strip=True)
            else:
                content = ""

            # Clean apostrophe from day names like "Jum'at" -> "Jumat"
            publish_date_str_clean = publish_date_str.replace("'", "")
            publish_date = self.parse_date(publish_date_str_clean)
            if not publish_date:
                logging.error(
                    f"Bisnis date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
