"""
Harian Jogja scraper — custom CMS search with HTML parsing.

https://www.harianjogja.com/search?q={keyword}
Article pattern: https://{subdomain}.harianjogja.com/r-{id}/{slug}
Subdomains: news, jogjapolitan, wisata, ekbis, ototekno, sport, jateng,
            ecologic, leisure, pendidikan, opini, cekfakta, www
"""

import logging                           # logging first
import json                              # stdlib imports alphabetically
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class HarianJogjaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.harianjogja.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_re = re.compile(
            r"^https?://[a-z0-9.-]*\.harianjogja\.com/r-\d+/"
        )

    async def build_search_url(self, keyword, page):
        if page == 1:
            url = f"{self.base_url}/search?q={keyword}"
        else:
            url = f"{self.base_url}/search?q={keyword}&page={page}"
        return await self.fetch(url, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")

        links = set()
        for a in soup.select("a[href]"):
            href = a["href"]
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                links.add(full_url)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning("No response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        # Title
        title_el = soup.select_one('meta[property="og:title"]')
        title = title_el.get("content", "").strip() if title_el else ""
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        if not title:
            return

        # Content
        content_div = soup.select_one(".article-content")
        if not content_div:
            content_div = soup.select_one(".post-content")
        if not content_div:
            content_div = soup.select_one(".entry-content")
        if not content_div:
            content_div = soup.select_one("article")
        if not content_div:
            return

        for tag in content_div.find_all(["script", "style", "iframe"]):
            tag.extract()
        # Remove related/ads/sidebar sections
        for tag in content_div.find_all(
            ["section", "div", "footer"],
            class_=re.compile(
                r"related|popular|most|sidebar|share|social|newsletter|ad|subscribe|embed|block_related|recommended|trending|tag|comment",
                re.IGNORECASE,
            ),
        ):
            tag.extract()

        content = content_div.get_text(separator=" ", strip=True)
        if not content:
            return

        # Date extraction
        publish_date = self._extract_date(soup, link)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        # Author
        author = self._extract_author(soup)

        # Category
        category = self._extract_category(soup)

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "harianjogja.com",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_date(self, soup, link):
        """Extract publish date from meta tags or JSON-LD."""
        # Try meta article:published_time
        date_meta = soup.select_one('meta[property="article:published_time"]')
        if date_meta and date_meta.get("content"):
            parsed = self.parse_date(date_meta["content"])
            if parsed:
                return parsed

        # Try JSON-LD datePublished
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        date_str = data.get("datePublished", "")
                        if date_str:
                            parsed = self.parse_date(date_str)
                            if parsed:
                                return parsed
                    # Handle @graph arrays
                    if isinstance(data, list):
                        for entry in data:
                            if isinstance(entry, dict):
                                date_str = entry.get("datePublished", "")
                                if date_str:
                                    parsed = self.parse_date(date_str)
                                    if parsed:
                                        return parsed
                except (json.JSONDecodeError, AttributeError):
                    continue

        logging.debug("Harian Jogja date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        """Extract author from meta tags or JSON-LD."""
        # Try meta article:author
        author_meta = soup.select_one('meta[property="article:author"]')
        if author_meta and author_meta.get("content"):
            content = author_meta["content"].strip()
            if content and not content.startswith("http"):
                return content

        # Try meta name="author"
        author_meta2 = soup.select_one('meta[name="author"]')
        if author_meta2 and author_meta2.get("content"):
            return author_meta2["content"].strip()

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            if script and script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        author_data = data.get("author", {})
                        if isinstance(author_data, dict):
                            name = author_data.get("name", "")
                            if name:
                                return name
                        elif isinstance(author_data, str) and author_data:
                            return author_data
                    if isinstance(data, list):
                        for entry in data:
                            if isinstance(entry, dict):
                                author_data = entry.get("author", {})
                                if isinstance(author_data, dict):
                                    name = author_data.get("name", "")
                                    if name:
                                        return name
                                elif isinstance(author_data, str) and author_data:
                                    return author_data
                except (json.JSONDecodeError, AttributeError):
                    continue

        return "Unknown"

    def _extract_category(self, soup):
        """Extract category from article page."""
        # Try meta article:section
        section_meta = soup.select_one('meta[property="article:section"]')
        if section_meta and section_meta.get("content"):
            return section_meta["content"].strip()

        # Try breadcrumb links
        for a in soup.select('a[href*="/"]'):
            href = a["href"]
            match = re.search(
                r"//(news|jogjapolitan|wisata|ekbis|ototekno|sport|jateng|ecologic|leisure|pendidikan|opini|cekfakta)\.",
                href,
            )
            if match:
                subdomain = match.group(1)
                return subdomain.capitalize()

        return "Unknown"

    async def build_latest_url(self, page):
        if page == 1:
            return await self.fetch(self.base_url, timeout=30)
        return await self.fetch(f"{self.base_url}/", timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a["href"]
            full_url = urljoin(self.base_url, href) if not href.startswith("http") else href
            if self._article_re.match(full_url):
                links.add(full_url)
        return links or None
