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
