import logging

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TribunnewsScraper(BaseScraper):
    """
    Tribunnews scraper implementation.

    Uses async HTTP requests to prevent event loop blocking.
    Implements tag pages as primary search method with fallback to search endpoint.
    """

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.tribunnews.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10  # Limit pages to prevent infinite scraping
        # Headers for anti-bot protection
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",  # Remove 'br' to avoid brotli requirement
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    async def build_search_url(self, keyword, page):
        """Build search URL using tag pages or search endpoint"""
        # Tag pages provide better results than search
        # Try tag page first, fall back to search if tag doesn't exist
        if page == 1:
            url = f"{self.base_url}/tag/{keyword.replace(' ', '-').lower()}"
        else:
            url = f"{self.base_url}/tag/{keyword.replace(' ', '-').lower()}?page={page}"

        # Use async fetch from BaseScraper with timeout
        response_text = await self.fetch(url, headers=self.headers, timeout=30)
        if response_text:
            return response_text

        # If tag page doesn't work (404 or empty), try search as fallback
        url = f"{self.base_url}/search?q={keyword.replace(' ', '+')}&page={page}"
        response_text = await self.fetch(url, headers=self.headers, timeout=30)
        return response_text

    def parse_article_links(self, response_text):
        """Parse article links from HTML response"""
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")

        # Try multiple selectors for article links
        articles = soup.select("h3 a[href]")
        if not articles:
            articles = soup.select(".txt a[href]")
        if not articles:
            articles = soup.select("a.txt[href]")
        if not articles:
            # Fallback for search page results
            articles = soup.select(
                "a[href*='/news/'], a[href*='/regional/'], a[href*='/bisnis/'], a[href*='/sport/']"
            )

        if not articles:
            return None

        # Extract and filter article URLs
        article_urls = set()
        for a in articles:
            href = a.get("href", "")
            if href:
                # Make absolute URL if needed
                if not href.startswith("http"):
                    if href.startswith("/"):
                        href = f"{self.base_url}{href}"
                    else:
                        href = f"{self.base_url}/{href}"

                # Filter out non-article links
                if any(
                    section in href
                    for section in [
                        "/news/",
                        "/regional/",
                        "/bisnis/",
                        "/sport/",
                        "/nasional/",
                        "/tribunners/",
                        "/lifestyle/",
                        "/new-economy/",
                    ]
                ):
                    # Exclude video/photo galleries
                    if not any(
                        exclude in href for exclude in ["/video/", "/foto/", "/galeri/"]
                    ):
                        # Clean mobile URLs
                        href = href.replace(
                            "https://m.tribunnews.com", "https://www.tribunnews.com"
                        )
                        article_urls.add(href)

        return article_urls if article_urls else None

    async def fetch_search_results(self, keyword):
        """Override to add page limit"""
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

            page += 1

        if not found_articles:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def get_article(self, link, keyword):
        """Fetch and parse individual article"""
        # Use async fetch with timeout
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            # Category extraction
            breadcrumb = soup.select_one(".breadcrumb")
            if breadcrumb:
                category_items = breadcrumb.select("a")
                # Skip 'Home' and get the actual category
                category = " > ".join(
                    [
                        item.get_text(strip=True)
                        for item in category_items[
                            1:3
                        ]  # Usually second and third items
                        if item.get_text(strip=True)
                    ]
                )
            else:
                category = "Unknown"

            # Title extraction
            title_elem = soup.select_one("h1#arttitle") or soup.select_one("h1.f50")
            if not title_elem:
                logging.error(f"Title not found for article {link}")
                return
            title = title_elem.get_text(strip=True)

            # Author extraction
            author_elem = soup.select_one(".author") or soup.select_one("div#penulis")
            if author_elem:
                author_text = author_elem.get_text(strip=True)
                # Extract author name, usually before "Kompas.com" or after "Penulis:"
                if "Penulis:" in author_text:
                    author = author_text.split("Penulis:")[1].split("|")[0].strip()
                elif "Editor:" in author_text:
                    # Get penulis, not editor
                    author = author_text.split("|")[0].strip()
                else:
                    author = author_text.split("-")[0].strip()
            else:
                author = "Unknown"

            # Date extraction
            date_elem = soup.select_one("time") or soup.select_one("div.grey.w100.mt10")
            if date_elem:
                # Get the datetime attribute if available, otherwise get text
                if date_elem.has_attr("datetime"):
                    publish_date_str = date_elem["datetime"]
                else:
                    publish_date_str = date_elem.get_text(strip=True)
                    # Clean up the date string (remove day name if present)
                    if "," in publish_date_str:
                        publish_date_str = publish_date_str.split(",")[1].strip()
            else:
                # Try meta tag
                meta_date = soup.find("meta", {"property": "article:published_time"})
                publish_date_str = meta_date.get("content", "") if meta_date else ""

            # Content extraction
            content_div = soup.select_one(".txt-article") or soup.select_one(".content")
            if not content_div:
                # Try alternative selector
                content_div = soup.select_one("div.side-article.txt-article")

            if content_div:
                # Remove unwanted elements
                for tag in content_div.find_all(["script", "style"]):
                    tag.extract()

                # Remove ads and related articles
                for tag in content_div.find_all(["div", "table"]):
                    if tag and any(
                        cls in str(tag.get("class", [])).lower()
                        for cls in ["baca-juga", "related", "iklan", "ads", "video"]
                    ):
                        tag.extract()

                # Remove specific text patterns
                for tag in content_div.find_all("p"):
                    text = tag.get_text()
                    if any(
                        phrase in text
                        for phrase in [
                            "Baca juga:",
                            "BACA JUGA:",
                            "Simak breaking news",
                            "dapatkan update",
                            "Ikuti kami di",
                        ]
                    ):
                        tag.extract()

                content = content_div.get_text(separator=" ", strip=True)
            else:
                content = ""

            if not content:
                return

            # Parse date
            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.error(
                    f"Tribunnews date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
                )
                return

            # Check date filter
            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            # Create item
            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "tribunnews.com",
                "link": link,
            }
            await self.queue_.put(item)

        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
            return
