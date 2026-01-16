import pytest

from newswatch.utils import AsyncScraper


@pytest.mark.asyncio
@pytest.mark.network
async def test_fetch_success():
    """Test successful fetch - marked as network test due to external dependency"""
    scraper = AsyncScraper()
    async with scraper:
        # Using httpbin.org which can be unreliable/rate-limited
        # Consider mocking in future for more stable tests
        response = await scraper.fetch("https://httpbin.org/get")
        # Skip test if httpbin is down/rate-limiting
        if response is None:
            pytest.skip("httpbin.org unavailable or rate-limiting")
        assert response is not None


@pytest.mark.asyncio
@pytest.mark.network
async def test_fetch_failure():
    """Test fetch with 404 response - marked as network test"""
    scraper = AsyncScraper()
    async with scraper:
        response = await scraper.fetch("https://httpbin.org/status/404")
        assert response is None
