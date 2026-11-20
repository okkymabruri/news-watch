import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from newswatch.utils import (
    AsyncScraper,
    _looks_blocked,
    keyword_matches_url,
    keyword_url_slug,
)


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
@pytest.mark.parametrize("rnet_available", [True, False])
async def test_blocked_http_fallback_with_optional_rnet(monkeypatch, rnet_available):
    from newswatch import utils

    body = "<html><h1>Article</h1><p>News content.</p></html>"
    rnet_get = AsyncMock(return_value=SimpleNamespace(status=200, text=AsyncMock(return_value=body)))
    client = MagicMock(return_value=SimpleNamespace(get=rnet_get))
    monkeypatch.setitem(sys.modules, "rnet", SimpleNamespace(Client=client, Proxy=MagicMock())
                        if rnet_available else None)
    browser_get = AsyncMock(return_value=body)
    monkeypatch.setattr(utils, "_playwright_get", browser_get)

    response = MagicMock()
    response.raise_for_status.side_effect = utils.aiohttp.ClientResponseError(
        request_info=None, history=(), status=403, message="Forbidden"
    )
    request = MagicMock()
    request.__aenter__ = AsyncMock(return_value=response)
    request.__aexit__ = AsyncMock(return_value=False)
    scraper = AsyncScraper()
    scraper.session = SimpleNamespace(headers={}, get=MagicMock(return_value=request))

    assert await scraper.fetch("https://example.org/article") == body
    if rnet_available:
        rnet_get.assert_awaited_once()
        browser_get.assert_not_awaited()
    else:
        browser_get.assert_awaited_once()


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


class TestKeywordUrlSlug:
    """Multi-word keywords must reach a publisher as a hyphenated path segment."""

    @pytest.mark.parametrize(
        "keyword,expected",
        [
            ("makan bergizi gratis", "makan-bergizi-gratis"),
            ("program MBG", "program-mbg"),
            ("satuan pelayanan pemenuhan gizi", "satuan-pelayanan-pemenuhan-gizi"),
            ("MBG", "mbg"),
            ("  padded  keyword  ", "padded-keyword"),
            ("tab\tseparated", "tab-separated"),
        ],
    )
    def test_slugifies_whitespace(self, keyword, expected):
        assert keyword_url_slug(keyword) == expected

    def test_matches_hyphenated_url(self):
        url = "https://www.liputan6.com/news/read/1/korupsi-makan-bergizi-gratis-naik"
        assert keyword_matches_url("makan bergizi gratis", url)

    def test_matches_verbatim_single_word(self):
        assert keyword_matches_url("mbg", "https://news.detik.com/berita/d-1/kasus-mbg")

    def test_rejects_absent_keyword(self):
        url = "https://www.liputan6.com/news/read/1/harga-pangan-turun"
        assert not keyword_matches_url("makan bergizi gratis", url)
        assert not keyword_matches_url("mbg", url)
