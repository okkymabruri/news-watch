"""
Minimal scraper tests - validate that each Linux-compatible scraper can get real data.
These tests use minimal data requirements and are designed for CI environments.
"""

from datetime import datetime, timedelta

import os

import pytest

from newswatch.api import scrape


KEYWORDS_BY_SCRAPER = {
    # Metrotvnews search can be flaky for finance terms (e.g. IHSG) in short windows.
    "metrotvnews": "prabowo",
}

# Linux-compatible scrapers (excluded ones that are known to fail on Linux/CI)
LINUX_SCRAPERS = [
    "antaranews",
    "bisnis",
    "bloombergtechnoz",
    "cnbcindonesia",
    "cnnindonesia",
    "detik",
    "idntimes",
    "jawapos",
    "kompas",
    "kontan",
    "kumparan",
    "liputan6",
    "merdeka",
    "metrotvnews",
    "okezone",
    "republika",
    "suara",
    "tempo",
    "tirto",
    "tribunnews",
    "viva",
    "mediaindonesia",
]


LINUX_EXCLUDED_SCRAPERS = [
    "katadata",  # search API requires bearer token capture; may fail in CI
]


@pytest.mark.network
@pytest.mark.parametrize("scraper", LINUX_SCRAPERS)
def test_scraper_minimal_data(scraper):
    """Test that each scraper can get at least 1 article with minimal requirements."""

    # Use 7-day range to ensure content availability
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        keywords = KEYWORDS_BY_SCRAPER.get(scraper, "ihsg")
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
        # Some sources can return short/preview-like content for certain entries,
        # so pick the first article that satisfies minimum length requirements.
        article = next(
            (
                a
                for a in articles
                if (a.get("title") and len(a.get("title") or "") > 5)
                and (a.get("content") and len(a.get("content") or "") > 50)
            ),
            articles[0],
        )
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


@pytest.mark.network
@pytest.mark.parametrize("scraper", LINUX_EXCLUDED_SCRAPERS)
def test_linux_excluded_scrapers_force_all(scraper):
    """Optional: run known-flaky Linux-excluded scrapers when explicitly requested.

    Enable with: NEWSWATCH_TEST_FORCE_ALL=1
    """

    if os.getenv("NEWSWATCH_TEST_FORCE_ALL") != "1":
        pytest.skip(
            "Set NEWSWATCH_TEST_FORCE_ALL=1 to run Linux-excluded scraper tests"
        )

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    keywords = "prabowo"

    try:
        articles = scrape(
            keywords=keywords,
            start_date=week_ago,
            scrapers=scraper,
            timeout=90,
        )
    except Exception as e:
        pytest.xfail(f"{scraper} appears blocked/unsupported in this environment: {e}")

    if not articles:
        pytest.xfail(
            f"{scraper} returned no results (likely blocked) for keyword='{keywords}'"
        )

    assert len(articles) >= 1
