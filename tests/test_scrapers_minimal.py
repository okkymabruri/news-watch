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
    "katadata",
    "jakartapost",
    "sindonews",
    "tvone",
    "tvrinews",
    "inews",
]


LINUX_EXCLUDED_SCRAPERS = []


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

    assert len(articles) >= 1


NONSENSE_KEYWORD = "xyznonexistent999zzz"


@pytest.mark.network
@pytest.mark.parametrize("scraper", LINUX_SCRAPERS)
def test_scraper_nonsense_keyword_returns_none(scraper):
    """Verify scrapers do not return articles for a keyword that cannot match.

    Exceptions are NOT swallowed: a scraper that fails to query must fail
    this test rather than silently pass with zero results.
    """

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    articles = scrape(
        keywords=NONSENSE_KEYWORD,
        start_date=week_ago,
        scrapers=scraper,
        timeout=60,
    )

    assert len(articles) == 0, (
        f"{scraper} returned {len(articles)} articles for nonsense keyword "
        f"'{NONSENSE_KEYWORD}' - first title: {articles[0].get('title', '')[:80]}"
    )


@pytest.mark.network
@pytest.mark.parametrize("scraper", LINUX_SCRAPERS)
def test_scraper_positive_relevance(scraper):
    """Verify scrapers return articles that actually contain the queried keyword."""

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    keywords = KEYWORDS_BY_SCRAPER.get(scraper, "ihsg")
    kw_lower = keywords.lower()

    articles = scrape(
        keywords=keywords,
        start_date=week_ago,
        scrapers=scraper,
        timeout=60,
    )

    assert len(articles) >= 1, (
        f"{scraper} returned no articles for '{keywords}' in last 7 days"
    )

    match = next(
        (
            a
            for a in articles
            if (
                kw_lower in (a.get("title") or "").lower()
                or kw_lower in (a.get("link") or "").lower()
                or kw_lower in (a.get("content") or "").lower()
            )
        ),
        None,
    )

    assert match is not None, (
        f"{scraper} returned {len(articles)} articles but none contain "
        f"keyword '{keywords}' in title, link, or content. "
        f"First title: '{(articles[0].get('title') or '')[:80]}'"
    )


@pytest.mark.network
def test_scraper_sindonews_no_duplicates():
    """Verify sindonews does not return duplicate articles across pagination."""

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    articles = scrape(
        keywords="ihsg",
        start_date=week_ago,
        scrapers="sindonews",
        timeout=120,
    )

    assert len(articles) >= 1, "sindonews returned no articles"

    links = [a.get("link") for a in articles if a.get("link")]
    unique_links = set(links)
    assert len(links) == len(unique_links), (
        f"sindonews returned {len(links)} articles but only "
        f"{len(unique_links)} unique links — duplicates detected"
    )
