"""
BeritaSatu scraper — uses /search/{keyword} endpoint for keyword search.
Custom CMS (not WordPress). CloudFront CDN blocks default UA but Chrome UA works.
"""

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper

ARTICLE_URL_RE = re.compile(r"^https?://www\.beritasatu\.com/[a-z]+/\d+/.+")


class BeritaSatuScraper(BaseScraper):
    """
    BeritaSatu scraper implementation.

    Search: https://www.beritasatu.com/search/{keyword}
    Pagination: ?page=N appended to search URL.
    Latest: homepage for page 1, /page/{N} for later.
    """

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.beritasatu.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10

    async def build_search_url(self, keyword, page):
        """Build search URL. Path param for keyword, query param for page."""
        url = f"{self.base_url}/search/{quote(keyword.lower())}"
        if page > 1:
            url += f"?page={page}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        """Extract article links matching the BeritaSatu URL pattern."""
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        filtered_hrefs = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ARTICLE_URL_RE.match(href):
                filtered_hrefs.add(href)

        return filtered_hrefs if filtered_hrefs else None

    def _extract_date(self, soup, link):
        """Extract publish date from multiple sources."""
        # Try meta article:published_time
        meta_time = soup.find("meta", {"property": "article:published_time"})
        if meta_time and meta_time.get("content"):
            date_str = meta_time["content"].strip()
            parsed = self.parse_date(date_str)
            if parsed:
                return parsed

        # Try JSON-LD datePublished
        json_ld_scripts = soup.find_all("script", type="application/ld+json")
        for script in json_ld_scripts:
            if script.string:
                import json

                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        date_str = data.get("datePublished") or data.get("datePublished", "")
                    elif isinstance(data, list):
                        date_str = data[0].get("datePublished") if data else ""
                    if date_str:
                        parsed = self.parse_date(date_str)
                        if parsed:
                            return parsed
                except json.JSONDecodeError:
                    pass

        # Try time element
        time_elem = soup.find("time")
        if time_elem:
            date_str = time_elem.get("datetime") or time_elem.get_text(strip=True)
            if date_str:
                parsed = self.parse_date(date_str)
                if parsed:
                    return parsed

        logging.debug("BeritaSatu date parse failed | url: %s", link)
        return None

    def _extract_author(self, soup):
        """Extract author from meta tags or JSON-LD."""
        # Try meta name="author"
        meta_author = soup.find("meta", {"name": "author"})
        if meta_author and meta_author.get("content"):
            author = meta_author["content"].strip()
            if author:
                return author

        # Try meta property="article:author"
        meta_author2 = soup.find("meta", {"property": "article:author"})
        if meta_author2 and meta_author2.get("content"):
            return meta_author2["content"].strip()

        # Try JSON-LD author
        json_ld_scripts = soup.find_all("script", type="application/ld+json")
        for script in json_ld_scripts:
            if script.string:
                import json

                try:
                    data = json.loads(script.string)
                    author_data = None
                    if isinstance(data, dict):
                        author_data = data.get("author")
                    elif isinstance(data, list):
                        author_data = data[0].get("author") if data else None
                    if author_data:
                        if isinstance(author_data, str):
                            return author_data
                        if isinstance(author_data, dict):
                            return author_data.get("name", "").strip()
                except json.JSONDecodeError:
                    pass

        return "Unknown"

    async def get_article(self, link, keyword):
        """Fetch and parse a single article page."""
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")

        try:
            # Title: meta og:title -> h1 fallback
            meta_og = soup.find("meta", {"property": "og:title"})
            if meta_og and meta_og.get("content"):
                title = meta_og["content"].strip()
            else:
                h1 = soup.select_one("h1")
                title = h1.get_text(strip=True) if h1 else ""

            if not title:
                logging.error(f"BeritaSatu title not found for article {link}")
                return

            # Author
            author = self._extract_author(soup)

            # Category: meta article:section or URL path segment
            meta_section = soup.find("meta", {"property": "article:section"})
            if meta_section and meta_section.get("content"):
                category = meta_section["content"].strip()
            else:
                # Extract from URL path: /category/id/slug
                match = re.match(r"https?://www\.beritasatu\.com/([a-z]+)/\d+/", link)
                category = match.group(1) if match else ""

            # Content extraction with fallback selectors
            content_div = None
            for selector in [".article-content", ".post-content", ".entry-content", "article"]:
                content_div = soup.select_one(selector)
                if content_div:
                    break

            if not content_div:
                logging.error(f"BeritaSatu content not found for article {link}")
                return

            # Remove script/style/iframe elements
            for tag in content_div.find_all(["script", "style", "iframe"]):
                tag.extract()

            # Remove related/popular/sidebar/ad elements via regex class matching
            remove_patterns = re.compile(r"related|popular|sidebar|ad|recommend|share|comment|social|tag|newsletter|subscribe|trending|widget|banner|promo|sponsor", re.I)
            for tag in content_div.find_all(True):
                classes = tag.get("class", [])
                if any(remove_patterns.search(c) for c in classes):
                    tag.extract()

            content = content_div.get_text(separator=" ", strip=True)
            if not content:
                return

            # Date parsing
            publish_date = self._extract_date(soup, link)
            if not publish_date:
                logging.error(f"BeritaSatu date parse failed | url: {link}")
                return

            # Date filtering
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
                "source": "beritasatu.com",
                "link": link,
            }
            await self.queue_.put(item)

        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")

    async def build_latest_url(self, page):
        """Build latest/index page URL."""
        if page == 1:
            url = self.base_url
        else:
            url = f"{self.base_url}/page/{page}"
        return await self.fetch(url)

    def parse_latest_article_links(self, response_text):
        """Extract article links from latest/index page."""
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        filtered_hrefs = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ARTICLE_URL_RE.match(href):
                filtered_hrefs.add(href)

        return filtered_hrefs if filtered_hrefs else None
