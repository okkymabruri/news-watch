"""
Minimal scraper tests - validate that each Linux-compatible scraper can get real data.
These tests use minimal data requirements and are designed for CI environments.
"""

from datetime import datetime, timedelta

import pytest

from newswatch.api import scrape

# Linux-compatible scrapers (excluded ones that are known to fail on Linux/CI)
LINUX_SCRAPERS = [
    "antaranews",
    "bisnis",
    "bloombergtechnoz",
    "cnbcindonesia",
    "cnnindonesia",
    "detik",
    "kompas",
    "liputan6",
    # "metrotvnews",  # disabled: timeout issues in CI
    "okezone",
    "tempo",
    "viva",
    "mediaindonesia",
]


@pytest.mark.network
@pytest.mark.parametrize("scraper", LINUX_SCRAPERS)
def test_scraper_minimal_data(scraper):
    """Test that each scraper can get at least 1 article with minimal requirements."""

    # Use 7-day range to ensure content availability
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        # Use the same keyword across scrapers to keep the test consistent.
        keywords = "ihsg"
        articles = scrape(
            keywords=keywords,
            start_date=week_ago,
            scrapers=scraper,
            timeout=60,  # 1 minute timeout per scraper
        )

        # Minimal validation - just check basic functionality
        assert len(articles) >= 1, (
            f"{scraper} returned no articles with '{keywords}' keyword in last 7 days"
        )

        # Validate article structure
        article = articles[0]
        assert article.get("title"), f"{scraper} article missing title"
        assert article.get("content"), f"{scraper} article missing content"
        # Check source (might be 'kompas' or 'kompas.com' format)
        assert scraper in article.get("source", "").lower(), (
            f"{scraper} not found in source: {article.get('source')}"
        )
        assert article.get("link"), f"{scraper} article missing link"

        # Check that content has reasonable length (not empty or error message)
        assert len(article["content"]) > 50, (
            f"{scraper} content too short: {len(article['content'])} chars"
        )
        assert len(article["title"]) > 5, (
            f"{scraper} title too short: {len(article['title'])} chars"
        )

        print(
            f"{scraper}: {len(articles)} articles, title: '{article['title'][:50]}...'"
        )

    except Exception as e:
        # Log the error but provide context about what we were testing
        pytest.fail(f"{scraper} scraper failed: {str(e)}")
