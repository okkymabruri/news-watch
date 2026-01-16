import pytest

from newswatch.scrapers.basescraper import BaseScraper


class DummyScraper(BaseScraper):
    async def build_search_url(self, keyword, page):
        return "https://example.com"

    def parse_article_links(self, response_text):
        return []

    async def get_article(self, link, keyword):
        pass


@pytest.mark.asyncio
async def test_basescraper_initialization():
    scraper = DummyScraper("test_keyword")
    assert scraper.keywords == ["test_keyword"]
    assert scraper.queue_ is None
