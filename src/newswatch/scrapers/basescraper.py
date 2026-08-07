import logging
from abc import ABC, abstractmethod

import dateparser

from ..timeutils import to_project_naive
from ..utils import AsyncScraper


class BaseScraper(AsyncScraper, ABC):
    # Search results are not always strictly reverse-chronological. Stopping at
    # the first page containing an out-of-window article ends pagination on one
    # stray result, which over a long window silently truncates a source.
    STALE_PAGE_TOLERANCE = 3

    def __init__(
        self,
        keywords,
        concurrency=10,
        queue_=None,
        max_latest_pages=None,
        dedup_links=None,
        start_datetime=None,
        end_datetime=None,
        max_pages=None,
        keyword_concurrency=None,
    ):
        super().__init__(concurrency, keyword_concurrency=keyword_concurrency)
        self.keywords = (
            [keyword.strip() for keyword in keywords.split(",") if keyword.strip()]
            if keywords
            else []
        )
        self.queue_ = queue_
        self.continue_scraping = True
        self._stale_pages = 0
        self.max_latest_pages = max_latest_pages if max_latest_pages is not None else 1
        self.max_pages = max_pages
        self.dedup_links = dedup_links or set()
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self._articles_collected = 0

    def parse_date(self, date_string, **kwargs):
        parsed_date = dateparser.parse(date_string, **kwargs)
        if parsed_date:
            # convert the offset, don't discard it: a -04:00 and a +07:00
            # article are 11 hours apart, not the same instant
            return to_project_naive(parsed_date)
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

    def _reset_pagination(self):
        """Clear pagination state at the start of a keyword or latest run."""
        self.continue_scraping = True
        self._stale_pages = 0

    def _keep_paginating(self, page_in_window):
        """Record one page's outcome; True to request the next page.

        ``continue_scraping`` is re-armed so the flag reports on the page just
        fetched rather than latching for the rest of the run.
        """
        self._stale_pages = 0 if page_in_window else self._stale_pages + 1
        self.continue_scraping = True
        return self._stale_pages < self.STALE_PAGE_TOLERANCE

    async def fetch_search_results(self, keyword):
        page = 1
        found_articles = False
        self._reset_pagination()

        while self.max_pages is None or page <= self.max_pages:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break

            filtered_hrefs = self.parse_article_links(response_text)
            if not filtered_hrefs:
                break

            found_articles = True
            in_window = await self.process_page(filtered_hrefs, keyword)
            if not self._keep_paginating(in_window):
                break

            page += 1

        if not found_articles:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")

    async def process_page(self, filtered_hrefs, keyword):
        links = self._filter_links(filtered_hrefs)
        if not links:
            return self.continue_scraping
        tasks = [self.get_article(href, keyword) for href in links]
        await self.run(tasks)
        return self.continue_scraping

    def _filter_links(self, links):
        """Filter links by dedup set before fetching articles."""
        if not self.dedup_links:
            return links
        return [link for link in links if link not in self.dedup_links]

    async def fetch_latest_results(self):
        page = 1
        found_articles = False
        self._reset_pagination()

        while page <= self.max_latest_pages:
            response_text = await self.build_latest_url(page)
            if not response_text:
                break

            filtered_hrefs = self.parse_latest_article_links(response_text)
            if not filtered_hrefs:
                break

            found_articles = True
            in_window = await self.process_page(filtered_hrefs, "latest")
            if not self._keep_paginating(in_window):
                break

            page += 1

        if not found_articles:
            logging.info(f"No latest news found on {self.base_url}")

    async def _run_keyword(self, keyword):
        if self.keyword_semaphore is None:
            await self.fetch_search_results(keyword)
        else:
            async with self.keyword_semaphore:
                await self.fetch_search_results(keyword)

    async def scrape(self, method="search"):
        async with self:
            if method == "latest":
                await self.fetch_latest_results()
            else:
                tasks = [self._run_keyword(keyword) for keyword in self.keywords]
                await self.run(tasks)
