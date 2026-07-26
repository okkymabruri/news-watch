import asyncio

from newswatch.scrapers.basescraper import BaseScraper


class DummyScraper(BaseScraper):
    async def build_search_url(self, keyword, page):
        return "https://example.com"

    def parse_article_links(self, response_text):
        return []

    async def get_article(self, link, keyword):
        pass


async def test_basescraper_initialization_normalizes_keywords_and_keeps_queue():
    queue = asyncio.Queue()
    scraper = DummyScraper("  ihsg ,  ekonomi , , saham  ", queue_=queue)
    assert scraper.keywords == ["ihsg", "ekonomi", "saham"]
    assert scraper.queue_ is queue


async def test_basescraper_initialization_empty_keywords_yield_empty_list():
    scraper = DummyScraper("")
    assert scraper.keywords == []


class _PaginationScraper(BaseScraper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visited_pages: list[int] = []

    async def build_search_url(self, keyword, page):
        self.visited_pages.append(page)
        return f"page-{page}"

    def parse_article_links(self, response_text):
        return [f"https://example.com/{response_text}"]

    async def get_article(self, link, keyword):
        pass


async def test_fetch_search_results_with_max_pages_two_stops_after_page_two():
    scraper = _PaginationScraper("ihsg", queue_=asyncio.Queue(), max_pages=2)
    await scraper.fetch_search_results("ihsg")
    assert scraper.visited_pages == [1, 2]


class _ConcurrencyTrackingScraper(BaseScraper):
    """Mimics a browser-required scraper: fetch_search_results does its own
    work directly, never calling self.fetch(), so only self.keyword_semaphore
    (not self.semaphore) can bound how many keyword tasks run at once."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active = 0
        self.max_active = 0

    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return []

    async def get_article(self, link, keyword):
        pass

    async def fetch_search_results(self, keyword):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1


async def test_scrape_without_keyword_concurrency_runs_keywords_unbounded():
    scraper = _ConcurrencyTrackingScraper(
        "a,b,c,d,e", queue_=asyncio.Queue(), keyword_concurrency=None
    )
    assert scraper.keyword_semaphore is None
    await scraper.scrape(method="search")
    assert scraper.max_active == 5


async def test_scrape_with_keyword_concurrency_one_runs_keywords_serially():
    scraper = _ConcurrencyTrackingScraper(
        "a,b,c,d,e", queue_=asyncio.Queue(), keyword_concurrency=1
    )
    await scraper.scrape(method="search")
    assert scraper.max_active == 1


async def test_scrape_with_keyword_concurrency_caps_parallel_keywords():
    scraper = _ConcurrencyTrackingScraper(
        "a,b,c,d,e,f", queue_=asyncio.Queue(), keyword_concurrency=2
    )
    await scraper.scrape(method="search")
    assert scraper.max_active <= 2


class _HttpPathScraper(BaseScraper):
    """Routes through self.fetch() like most scrapers -- proves
    keyword_concurrency=1 alongside concurrency=1 doesn't self-deadlock.
    If keyword_semaphore reused self.semaphore, a single task would try to
    acquire the same non-reentrant lock twice (once via _run_keyword, again
    inside fetch()) and hang forever."""

    async def build_search_url(self, keyword, page):
        return await self.fetch("https://example.com")

    def parse_article_links(self, response_text):
        return []

    async def get_article(self, link, keyword):
        pass


async def test_keyword_semaphore_distinct_from_fetch_semaphore_no_deadlock():
    from aioresponses import aioresponses

    scraper = _HttpPathScraper(
        "a,b", concurrency=1, queue_=asyncio.Queue(), keyword_concurrency=1
    )
    with aioresponses() as mocked:
        mocked.get("https://example.com", status=200, body="ok", repeat=True)
        await asyncio.wait_for(scraper.scrape(method="search"), timeout=2)
