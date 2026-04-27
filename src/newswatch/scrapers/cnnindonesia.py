"""
CNN Indonesia scraper — uses RSS feed with keyword filtering.

The site has no working search API, but RSS items can be filtered
by keyword presence in title or description.
"""

import logging

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class CNNIndonesiaScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.cnnindonesia.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.rss_urls = [
            f"{self.base_url}/{ch}/rss"
            for ch in ["nasional", "internasional", "ekonomi", "teknologi", "olahraga", "hiburan", "gaya-hidup"]
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }

    async def fetch_search_results(self, keyword):
        """Fetch all RSS feeds and filter by keyword."""
        kw_lower = keyword.lower()
        all_items = []

        for rss_url in self.rss_urls:
            try:
                response_text = await self.fetch(rss_url, headers=self.headers, timeout=30)
                if not response_text:
                    continue
                soup = BeautifulSoup(response_text, "xml")
                for item in soup.find_all("item"):
                    title_el = item.find("title")
                    desc_el = item.find("description")
                    link_el = item.find("link")
                    pub_el = item.find("pubDate")

                    title = title_el.get_text(strip=True) if title_el else ""
                    desc = desc_el.get_text(strip=True) if desc_el else ""
                    link = link_el.get_text(strip=True) if link_el else ""
                    pub_date_str = pub_el.get_text(strip=True) if pub_el else ""

                    if kw_lower not in title.lower() and kw_lower not in desc.lower():
                        continue

                    publish_date = self.parse_date(pub_date_str)
                    if not publish_date:
                        continue

                    if self.start_date and publish_date < self.start_date:
                        continue

                    all_items.append({
                        "title": title,
                        "publish_date": publish_date,
                        "author": "Unknown",
                        "content": desc,
                        "keyword": keyword,
                        "category": "Unknown",
                        "source": "cnnindonesia.com",
                        "link": link,
                    })
            except Exception as e:
                logging.debug(f"CNN RSS fetch failed for {rss_url}: {e}")

        if all_items:
            for item in all_items:
                await self.queue_.put(item)
        else:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def fetch_latest_results(self):
        """Fetch newest RSS items without keyword filtering."""
        all_items = []

        for rss_url in self.rss_urls:
            try:
                response_text = await self.fetch(
                    rss_url, headers=self.headers, timeout=30
                )
                if not response_text:
                    continue
                soup = BeautifulSoup(response_text, "xml")
                for item in soup.find_all("item")[:10]:
                    title_el = item.find("title")
                    desc_el = item.find("description")
                    link_el = item.find("link")
                    pub_el = item.find("pubDate")

                    title = title_el.get_text(strip=True) if title_el else ""
                    desc = desc_el.get_text(strip=True) if desc_el else ""
                    link = link_el.get_text(strip=True) if link_el else ""
                    pub_date_str = pub_el.get_text(strip=True) if pub_el else ""

                    publish_date = self.parse_date(pub_date_str)
                    if not publish_date:
                        continue

                    all_items.append(
                        {
                            "title": title,
                            "publish_date": publish_date,
                            "author": "Unknown",
                            "content": desc,
                            "keyword": "latest",
                            "category": "Unknown",
                            "source": "cnnindonesia.com",
                            "link": link,
                        }
                    )
            except Exception as e:
                logging.debug(f"CNN RSS fetch failed for {rss_url}: {e}")

        if all_items:
            seen_links = set()
            for item in sorted(all_items, key=lambda x: x["publish_date"], reverse=True)[
                :50
            ]:
                if item["link"] in seen_links:
                    continue
                seen_links.add(item["link"])
                await self.queue_.put(item)
        else:
            logging.info(f"No latest news found on {self.base_url}")

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def get_article(self, link, keyword):
        # Not used — articles processed via RSS
        pass
