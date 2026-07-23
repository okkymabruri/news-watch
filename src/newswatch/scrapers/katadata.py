import json
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_LATEST_URL = "https://katadata.co.id/indeks"
_ARTICLE_ID_RE = re.compile(r"[0-9a-fA-F]+")
_ARTICLE_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_NON_ARTICLE_PATHS = frozenset({
    "author", "category", "indeks", "kategori", "pencarian", "search",
    "tag", "tags", "topic", "topik",
})


class KatadataScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "katadata.co.id"
        self.api_url = "https://api-search.katadata.co.id/search"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        payload = {
            "q": keyword,
            "source": "katadata",
            "sort": "newest",
            "limit": 10,
            "page": page,
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }

        return await self.fetch(
            self.api_url,
            method="POST",
            data=json.dumps(payload),
            headers=headers,
            timeout=30,
        )

    def parse_article_links(self, response_text):
        try:
            response_json = json.loads(response_text)
        except Exception:
            return None

        articles = response_json.get("results", [])
        if not articles:
            return None

        filtered_hrefs = set()
        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "").lower()
            if url and any(
                keyword.lower() in url.lower() or keyword.lower() in title
                for keyword in self.keywords
            ):
                filtered_hrefs.add(url)

        return filtered_hrefs if filtered_hrefs else None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            category = soup.select_one(".section-breadcrumb")
            category = category.get_text(strip=True) if category else ""

            title = soup.select_one(".detail-title.mb-4")
            if title:
                title = title.get_text(strip=True)
            else:
                meta = soup.find("meta", {"property": "og:title"})
                title = meta.get("content", "").strip() if meta else ""

            if not title:
                logging.error(f"Katadata title not found for article {link}")
                return

            author = soup.select_one(".detail-author-name")
            if author:
                author = author.get_text(strip=True).replace("Oleh", "").strip()
            else:
                author = "Unknown"

            publish_date_str = ""
            date_elem = soup.select_one(".detail-date.text-gray")
            if date_elem:
                publish_date_str = date_elem.get_text(strip=True)
            else:
                meta = soup.find("meta", {"property": "article:published_time"})
                publish_date_str = meta.get("content", "") if meta else ""

            content_div = soup.select_one(".detail-main")
            if not content_div:
                content_div = soup.select_one("article")

            if content_div:
                for tag in content_div.find_all("div"):
                    classes = tag.get("class", [])
                    if tag and (
                        any(cls.startswith("widget-baca-juga") for cls in classes)
                        or any("ai-summary" in cls for cls in classes)
                    ):
                        tag.extract()
                content = content_div.get_text(separator="\n", strip=True)
            else:
                content = ""

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(
                    f"Katadata date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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

    async def build_latest_url(self, page):
        # Page 2+ uses a POST cursor, which latest mode does not support yet.
        if page > 1:
            return None
        return await self.fetch(_LATEST_URL)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = {
            link
            for anchor in soup.select("article.article--berita a[href]")
            if (link := self._canonical_article_url(anchor.get("href", "")))
        }
        return links or None

    @staticmethod
    def _canonical_article_url(href):
        if not isinstance(href, str) or not href.strip():
            return None
        parsed = urlparse(urljoin(f"{_LATEST_URL}/", href.strip()))
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc.lower() != "katadata.co.id"
            or parsed.params
        ):
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if (
            len(parts) < 2
            or any(part.lower() in _NON_ARTICLE_PATHS for part in parts[:-2])
            or not _ARTICLE_ID_RE.fullmatch(parts[-2])
            or not _ARTICLE_SLUG_RE.fullmatch(parts[-1])
        ):
            return None
        return f"https://katadata.co.id/{'/'.join(parts)}"
