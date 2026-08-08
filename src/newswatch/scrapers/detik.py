"""
Detik scraper — dated index walk for search, sitemaps as the fallback.

The search API is unreliable. ``/indeks?page=N&date=MM/DD/YYYY`` is dated and
paginated, so it reaches arbitrarily far back; the news sitemaps only span the
last day or so. When a start date is given the index walk is used, because the
sitemaps cannot answer for anything older.

Set ``NEWSWATCH_DETIK_INDEX_NEWEST=YYYY-MM-DD`` to start the walk at a day
other than today, so a long backfill can be resumed in chunks.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from .basescraper import BaseScraper
from ..utils import keyword_matches_url


class DetikScraper(BaseScraper):
    INDEX_HOSTS = ("news", "finance", "health")
    MAX_INDEX_PAGES_PER_DAY = 50
    INDEX_CHUNK = 10
    MAX_INDEX_DAYS = 800

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.detik.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.sitemap_urls = [
            "https://finance.detik.com/sitemap_news.xml",
            "https://news.detik.com/berita/sitemap_news.xml",
            "https://news.detik.com/ekonomi/sitemap_news.xml",
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }
        self.latest_href_pattern = re.compile(
            r"^https://news\.detik\.com/.+/d-\d+/"
        )
        self.index_href_pattern = re.compile(
            r"^https://(?:news|finance|health)\.detik\.com/.+/d-\d+/"
        )
        # the walk always starts at the newest day and reads backwards, so a
        # long backfill that dies partway has to restart from today. Naming
        # the newest day makes it resumable in chunks.
        self.index_newest_day = self._env_day("NEWSWATCH_DETIK_INDEX_NEWEST")

    @staticmethod
    def _env_day(name):
        value = os.environ.get(name)
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            logging.warning("%s=%r is not YYYY-MM-DD; ignoring", name, value)
            return None

    async def fetch_search_results(self, keyword):
        """Walk the dated index when a start date is set, else scan sitemaps."""
        if self.start_date:
            await self._walk_indeks(keyword)
        else:
            await self._scan_sitemaps(keyword)

    async def _walk_indeks(self, keyword):
        """Read ``/indeks`` day by day, newest first, matching on headline.

        The index carries no keyword facility, so headlines are the only way
        to avoid fetching every article detik published (~500/day). That is
        the same field the corpus relevance gate reads, so nothing survives
        the filter here that would survive downstream.
        """
        needle = " ".join(keyword.lower().split())
        today = self.index_newest_day or datetime.now().date()
        oldest = self.start_date.date()
        span = (today - oldest).days + 1
        if span > self.MAX_INDEX_DAYS:
            oldest = today - timedelta(days=self.MAX_INDEX_DAYS - 1)
            logging.warning(
                "Detik index walk is capped at %d days; not reading anything "
                "before %s for keyword '%s'",
                self.MAX_INDEX_DAYS,
                oldest.isoformat(),
                keyword,
            )

        matched = 0
        seen = set()
        truncated_days = 0
        day = today
        while day >= oldest:
            stamp = day.strftime("%m/%d/%Y")
            for host in self.INDEX_HOSTS:
                page = 1
                while page <= self.MAX_INDEX_PAGES_PER_DAY:
                    # 573 days x 3 channels is far too many round trips to walk
                    # one page at a time; self.fetch's semaphore still caps the
                    # real parallelism at the registry concurrency
                    chunk = range(page, min(page + self.INDEX_CHUNK, self.MAX_INDEX_PAGES_PER_DAY + 1))
                    results = await asyncio.gather(
                        *(
                            self._fetch_index_page(host, stamp, n)
                            for n in chunk
                        )
                    )
                    hits = 0
                    for cards, entries in results:
                        if not cards:
                            continue
                        hits += 1
                        for link, title in entries:
                            if link in seen:
                                continue
                            seen.add(link)
                            if needle in " ".join(title.lower().split()):
                                matched += 1
                                await self.get_article(link, keyword)
                    if not hits:
                        break
                    page = chunk.stop
                else:
                    truncated_days += 1
            day -= timedelta(days=1)

        if truncated_days:
            logging.warning(
                "Detik index hit the %d-page cap on %d channel-days for "
                "keyword '%s'; those days are partially read",
                self.MAX_INDEX_PAGES_PER_DAY,
                truncated_days,
                keyword,
            )
        if not matched:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def _fetch_index_page(self, host, stamp, page):
        url = f"https://{host}.detik.com/indeks?page={page}&date={stamp}"
        try:
            return self._parse_indeks(
                await self.fetch(url, headers=self.headers, timeout=30)
            )
        except Exception as e:
            logging.debug("Detik index fetch failed for %s: %s", url, e)
            return 0, []

    def _parse_indeks(self, response_text):
        """(card count, [(link, headline)]) for one index page.

        The raw card count is returned separately: pagination has to key on
        it, not on the filtered list, or a page of photo galleries reads as
        the end of the day.
        """
        if not response_text:
            return 0, []
        soup = BeautifulSoup(response_text, "html.parser")
        cards = soup.select("article")
        entries = []
        for card in cards:
            anchor = card.select_one("a[href]")
            if not anchor:
                continue
            link = anchor.get("href", "")
            if not self.index_href_pattern.match(link):
                continue
            if "20.detik.com" in link or "/foto-" in link:
                continue
            heading = card.select_one("h2, h3")
            title = heading.get_text(" ", strip=True) if heading else anchor.get("title", "")
            if title:
                entries.append((link, title))
        return len(cards), entries

    async def _scan_sitemaps(self, keyword):
        """Scan sitemaps and filter by keyword in URL."""
        all_links = set()

        for sm_url in self.sitemap_urls:
            try:
                response_text = await self.fetch(sm_url, headers=self.headers, timeout=30)
                if not response_text:
                    continue
                soup = BeautifulSoup(response_text, "xml")
                for loc in soup.find_all("loc"):
                    url = loc.text.strip()
                    if url and keyword_matches_url(keyword, url):
                        all_links.add(url)
            except Exception as e:
                logging.debug(f"Detik sitemap fetch failed for {sm_url}: {e}")

        if all_links:
            for link in list(all_links):
                await self.get_article(link, keyword)
        else:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def build_latest_url(self, page):
        return await self.fetch(
            f"https://news.detik.com/indeks?page={page}",
            headers=self.headers,
            timeout=30,
        )

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        filtered_hrefs = {
            a.get("href")
            for a in soup.select("article a[href]")
            if a.get("href")
            and self.latest_href_pattern.match(a.get("href"))
            and "20.detik.com" not in a.get("href")
            and "/foto-" not in a.get("href")
        }
        return filtered_hrefs or None

    async def get_article(self, link, keyword):
        try:
            response_text = await self.fetch(link, headers=self.headers, timeout=30)
            if not response_text:
                return

            soup = BeautifulSoup(response_text, "html.parser")

            title_el = soup.select_one("h1.detail__title") or soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                return

            date_el = soup.select_one("div.detail__date")
            publish_date_str = date_el.get_text(strip=True) if date_el else ""

            content_div = soup.select_one("div.detail__body-text") or soup.select_one("article")
            if not content_div:
                return
            paragraphs = [p.get_text(" ", strip=True) for p in content_div.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p) > 30]
            content = " ".join(paragraphs)
            if not content:
                content = content_div.get_text(" ", strip=True)
            if not content:
                return

            author_el = soup.select_one("div.detail__author")
            author = author_el.get_text(strip=True) if author_el else "Unknown"

            publish_date = self.parse_date(publish_date_str, locales=["id"])
            if not publish_date:
                logging.debug("Detik date parse failed | url: %s | date: %r", link, publish_date_str[:50])
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            category = "Unknown"
            cat_el = soup.select_one("div.detail__category a")
            if cat_el:
                category = cat_el.get_text(strip=True)

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "detik.com",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
