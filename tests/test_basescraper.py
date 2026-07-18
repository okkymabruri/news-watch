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