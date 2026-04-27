import logging
from abc import ABC, abstractmethod

import dateparser

from ..utils import AsyncScraper


class BaseScraper(AsyncScraper, ABC):
    def __init__(self, keywords, concurrency=10, queue_=None, max_latest_pages=None):
        super().__init__(concurrency)
        self.keywords = (
            [keyword.strip() for keyword in keywords.split(",") if keyword.strip()]
            if keywords
            else []
        )
        self.queue_ = queue_
        self.continue_scraping = True
        self.max_latest_pages = max_latest_pages if max_latest_pages is not None else 1

    def parse_date(self, date_string, **kwargs):
        parsed_date = dateparser.parse(date_string, **kwargs)
        if parsed_date:
            return parsed_date.replace(tzinfo=None)
        return None

    @abstractmethod
    async def build_search_url(self, keyword, page):
        pass

    @abstractmethod
    def parse_article_links(self, response_text):
        pass

    @abstractmethod
    async def get_article(self, link, keyword):
        pass

    async def build_latest_url(self, page):
        return None

    def parse_latest_article_links(self, response_text):
        return None

    async def fetch_search_results(self, keyword):
        page = 1
        found_articles = False

        while self.continue_scraping:
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

    async def process_page(self, filtered_hrefs, keyword):
        tasks = [self.get_article(href, keyword) for href in filtered_hrefs]
        await self.run(tasks)
        return self.continue_scraping

    async def fetch_latest_results(self):
        page = 1
        found_articles = False

        while self.continue_scraping and page <= self.max_latest_pages:
            response_text = await self.build_latest_url(page)
            if not response_text:
                break

            filtered_hrefs = self.parse_latest_article_links(response_text)
            if not filtered_hrefs:
                break

            found_articles = True
            continue_scraping = await self.process_page(filtered_hrefs, "latest")
            if not continue_scraping:
                break

            page += 1

        if not found_articles:
            logging.info(f"No latest news found on {self.base_url}")

    async def scrape(self, method="search"):
        async with self:
            if method == "latest":
                await self.fetch_latest_results()
            else:
                tasks = [
                    self.fetch_search_results(keyword) for keyword in self.keywords
                ]
                await self.run(tasks)
