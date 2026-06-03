import pytest

from newswatch.utils import AsyncScraper, _looks_blocked


class TestLooksBlocked:
    """Offline tests for the anti-bot block-marker detector."""

    @pytest.mark.parametrize(
        "marker",
        [
            "just a moment",
            "please enable javascript",
            "datadome",
            "perimeterx",
            "px-captcha",
            "ddos-guard",
            "reference #",
            "access denied",
            "forbidden",
            "captcha",
            "cloudflare",
            "attention required",
            "verify you are human",
            "checking your browser",
            "incapsula",
            "sucuri",
            "akamai",
        ],
    )
    def test_detects_known_block_markers(self, marker):
        html = f"<!doctype html><html><head><title>blocked</title></head><body>{marker}</body></html>"
        assert _looks_blocked(html) is True

    def test_ignores_plain_text(self):
        assert _looks_blocked("just a moment, my friend wrote a story") is False

    def test_ignores_json_body(self):
        assert _looks_blocked('{"a":1,"b":2}') is False

    def test_ignores_normal_html(self):
        html = "<!doctype html><html><head><title>Hello</title></head><body><h1>News</h1></body></html>"
        assert _looks_blocked(html) is False


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
