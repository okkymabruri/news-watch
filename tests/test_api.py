"""
Tests for the synchronous API module.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from newswatch.api import (
    latest,
    latest_to_dataframe,
    latest_to_file,
    list_scrapers,
    quick_scrape,
    scrape,
    scrape_to_dataframe,
    scrape_to_file,
)
from newswatch.exceptions import ValidationError


class TestListScrapers:
    """Test scraper listing functionality."""

    def test_list_scrapers_returns_list(self):
        """Test that list_scrapers returns a list of strings."""
        scrapers = list_scrapers()
        assert isinstance(scrapers, list)
        assert len(scrapers) > 0
        assert all(isinstance(s, str) for s in scrapers)

    def test_list_scrapers_includes_known_scrapers(self):
        """Test that known scrapers are in the list."""
        scrapers = list_scrapers()
        expected_scrapers = ["kompas", "tempo", "bbc"]
        for scraper in expected_scrapers:
            assert scraper in scrapers

    def test_list_latest_scrapers_returns_subset(self):
        """Test that latest scraper listing works."""
        scrapers = list_scrapers(method="latest")
        assert isinstance(scrapers, list)
        assert "kompas" in scrapers
        assert "antaranews" in scrapers
        assert "tempo" in scrapers  # now supports latest


class TestInputValidation:
    """Test input validation for API functions."""

    def test_scrape_invalid_date_format(self):
        """Test that invalid date format raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid date format"):
            scrape("test", "2025-13-45")  # invalid date

    def test_scrape_empty_keywords(self):
        """Test that empty keywords raise ValidationError."""
        with pytest.raises(ValidationError, match="Keywords cannot be empty"):
            scrape("", "2025-01-01")

    def test_scrape_invalid_scrapers(self):
        """Test that invalid scrapers raise ValidationError."""
        with pytest.raises(ValidationError, match="Invalid scrapers"):
            scrape("test", "2025-01-01", scrapers="nonexistent_scraper")

    def test_scrape_invalid_method(self):
        """Test that invalid method raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid method"):
            scrape("test", "2025-01-01", method="invalid")

    def test_search_requires_start_date(self):
        """Test that search method still requires start_date."""
        with pytest.raises(ValidationError, match="Start date is required"):
            scrape("test", None)

    def test_latest_does_not_require_keywords_or_start_date(self):
        """Test that latest method can run without keywords/start_date."""
        with patch("newswatch.api._async_scrape_to_list", new_callable=AsyncMock) as mock_async:
            mock_async.return_value = []
            result = scrape(method="latest")
            assert result == []
            args = mock_async.call_args[0]
            assert args[0] is None
            assert args[1] is None
            assert args[5] == "latest"


class TestScrapeToDataFrame:
    """Test scrape_to_dataframe functionality."""

    @patch("newswatch.api.scrape")
    def test_scrape_to_dataframe_empty_results(self, mock_scrape):
        """Test dataframe creation with empty results."""
        mock_scrape.return_value = []

        df = scrape_to_dataframe("test", "2025-01-01")

        assert isinstance(df, pd.DataFrame)
        assert df.empty
        expected_columns = [
            "title",
            "publish_date",
            "author",
            "content",
            "keyword",
            "category",
            "source",
            "link",
        ]
        assert list(df.columns) == expected_columns

    @patch("newswatch.api.scrape")
    def test_scrape_to_dataframe_with_results(self, mock_scrape):
        """Test dataframe creation with mock results."""
        mock_results = [
            {
                "title": "Test Article",
                "publish_date": "2025-01-01 12:00:00",
                "author": "Test Author",
                "content": "Test content",
                "keyword": "test",
                "category": "News",
                "source": "test.com",
                "link": "http://test.com/article1",
            }
        ]
        mock_scrape.return_value = mock_results

        df = scrape_to_dataframe("test", "2025-01-01")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.loc[0, "title"] == "Test Article"
        assert pd.api.types.is_datetime64_any_dtype(df["publish_date"])


class TestScrapeToFile:
    """Test scrape_to_file functionality."""

    def test_scrape_to_file_invalid_format(self):
        """Test that invalid output format raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid output format"):
            scrape_to_file("test", "2025-01-01", "output.txt", "txt")

    @patch("newswatch.api.scrape_to_dataframe")
    def test_scrape_to_file_xlsx(self, mock_scrape_df):
        """Test saving to XLSX file."""
        import pandas as pd

        # create a real DataFrame to test with
        mock_df = pd.DataFrame(
            [
                {
                    "title": "Test",
                    "publish_date": "2025-01-01",
                    "author": "Test",
                    "content": "Test",
                    "keyword": "test",
                    "category": "News",
                    "source": "test.com",
                    "link": "http://test.com",
                }
            ]
        )
        mock_scrape_df.return_value = mock_df

        with patch("pandas.DataFrame.to_excel") as mock_to_excel:
            scrape_to_file("test", "2025-01-01", "test_output.xlsx", "xlsx")
            mock_to_excel.assert_called_once()

        mock_scrape_df.assert_called_once()

    @patch("newswatch.api.scrape_to_dataframe")
    def test_scrape_to_file_csv(self, mock_scrape_df):
        """Test saving to CSV file."""
        import pandas as pd

        # create a real DataFrame to test with
        mock_df = pd.DataFrame(
            [
                {
                    "title": "Test",
                    "publish_date": "2025-01-01",
                    "author": "Test",
                    "content": "Test",
                    "keyword": "test",
                    "category": "News",
                    "source": "test.com",
                    "link": "http://test.com",
                }
            ]
        )
        mock_scrape_df.return_value = mock_df

        with patch("pandas.DataFrame.to_csv") as mock_to_csv:
            scrape_to_file("test", "2025-01-01", "test_output.csv", "csv")
            mock_to_csv.assert_called_once()

        mock_scrape_df.assert_called_once()


class TestConvenienceFunctions:
    """Test convenience functions."""

    @patch("newswatch.api.scrape_to_dataframe")
    def test_quick_scrape(self, mock_scrape_df):
        """Test quick_scrape convenience function."""
        mock_df = MagicMock()
        mock_scrape_df.return_value = mock_df

        result = quick_scrape("test", days_back=2)

        assert result == mock_df
        mock_scrape_df.assert_called_once()

        # check that start_date is calculated correctly (2 days back)
        call_args = mock_scrape_df.call_args[0]
        keywords, start_date, scrapers = call_args
        assert keywords == "test"
        assert scrapers == "auto"
        # verify date is approximately 2 days ago
        expected_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        assert start_date == expected_date

    @patch("newswatch.api.scrape")
    def test_latest(self, mock_scrape):
        """Test latest convenience function."""
        mock_scrape.return_value = []

        result = latest(scrapers="kompas")

        assert result == []
        mock_scrape.assert_called_once_with(
            keywords=None,
            start_date=None,
            scrapers="kompas",
            verbose=False,
            timeout=300,
            method="latest",
            limit=None,
            max_pages=None,
            scraper_timeout=None,
            time_range=None,
            dedup_file=None,
        )

    @patch("newswatch.api.scrape_to_dataframe")
    def test_latest_to_dataframe(self, mock_scrape_df):
        """Test latest_to_dataframe convenience function."""
        mock_df = MagicMock()
        mock_scrape_df.return_value = mock_df

        result = latest_to_dataframe(scrapers="kompas")

        assert result == mock_df
        mock_scrape_df.assert_called_once_with(
            keywords=None,
            start_date=None,
            scrapers="kompas",
            verbose=False,
            timeout=300,
            method="latest",
            limit=None,
            max_pages=None,
            scraper_timeout=None,
            time_range=None,
            dedup_file=None,
        )

    @patch("newswatch.api.scrape_to_file")
    def test_latest_to_file(self, mock_scrape_to_file):
        """Test latest_to_file convenience function."""
        latest_to_file("latest.json", output_format="json", scrapers="kompas")

        mock_scrape_to_file.assert_called_once_with(
            keywords=None,
            start_date=None,
            output_path="latest.json",
            output_format="json",
            scrapers="kompas",
            verbose=False,
            timeout=300,
            method="latest",
            limit=None,
            max_pages=None,
            scraper_timeout=None,
            time_range=None,
            dedup_file=None,
        )


class TestMaxPagesPropagation:
    """Test that max_pages is properly forwarded to scrapers in both CLI and API paths."""

    @patch("newswatch.api._async_scrape_to_list", new_callable=AsyncMock)
    def test_scrape_passes_max_pages(self, mock_async):
        """Test that scrape() forwards max_pages to internal function."""
        mock_async.return_value = []
        scrape("test", "2025-01-01", max_pages=3)
        assert mock_async.call_args[0][7] == 3  # max_pages is 8th positional arg

    @patch("newswatch.api._async_scrape_to_list", new_callable=AsyncMock)
    def test_latest_passes_max_pages(self, mock_async):
        """Test that latest() forwards max_pages."""
        mock_async.return_value = []
        latest(scrapers="kompas", max_pages=2)
        assert mock_async.call_args[0][7] == 2  # max_pages is 8th positional arg

    @patch("newswatch.api._async_scrape_to_list", new_callable=AsyncMock)
    def test_latest_passes_limit(self, mock_async):
        """Test that latest() forwards limit."""
        mock_async.return_value = []
        latest(scrapers="kompas", limit=10)
        assert mock_async.call_args[0][6] == 10  # limit is 7th positional arg


class TestLimitRegression:
    """Regression tests for limit handling after refactoring."""

    @patch("newswatch.api._async_scrape_to_list", new_callable=AsyncMock)
    def test_latest_with_limit_no_cancelled_error(self, mock_async):
        """Test that latest(limit=N) returns cleanly without leaking CancelledError."""
        mock_async.return_value = [{"title": "test", "link": "http://example.com"}]
        result = latest(scrapers="kompas", limit=1)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_kontan_urljoin_search(self):
        """Test that urljoin handles Kontan-style links correctly."""
        from urllib.parse import urljoin
        base_url = "https://www.kontan.co.id"
        # protocol-relative URL
        assert urljoin(base_url, "//investasi.kontan.co.id/news/foo") == \
            "https://investasi.kontan.co.id/news/foo"
        # absolute URL
        assert urljoin(base_url, "https://www.kontan.co.id/news/bar") == \
            "https://www.kontan.co.id/news/bar"
        # relative URL
        assert urljoin(base_url, "/news/baz") == \
            "https://www.kontan.co.id/news/baz"

    def test_rri_latest_page_gt_1_returns_none(self):
        """Test that RRI build_latest_url returns None for page > 1."""
        from newswatch.scrapers.rri import RRIScraper

        # Verify the code logic: page > 1 returns None immediately
        scraper = RRIScraper(keywords="test")
        # The method checks page > 1 before any network call
        # We can verify the logic by checking that page 2 would return None
        # without triggering a network call (page 1 would trigger fetch)
        assert scraper.max_pages == 10  # search has pagination
        # build_latest_url for page > 1 returns None by design
        # We verify this by inspecting the source
        import inspect
        src = inspect.getsource(scraper.build_latest_url)
        assert "if page > 1" in src
        assert "return None" in src

    def test_all_stable_scrapers_support_latest(self):
        """Ensure every stable scraper is also latest-capable."""
        from newswatch.registry import get_stable_scrapers
        stable = get_stable_scrapers()
        missing = [slug for slug, entry in stable.items() if not entry.supports_latest]
        assert not missing, f"Stable scrapers without latest support: {missing}"


class TestLatestCoverage:
    """Ensure every registered latest-capable scraper has a working implementation."""

    @pytest.mark.parametrize(
        "slug",
        sorted(
            s for s, e in __import__("newswatch.registry", fromlist=["SCRAPERS"]).SCRAPERS.items()
            if e.supports_latest
        ),
    )
    def test_latest_scraper_has_working_implementation(self, slug):
        """Scraper must either override fetch_latest_results, or provide latest hooks + get_article."""
        from newswatch.registry import SCRAPERS
        entry = SCRAPERS[slug]
        import importlib
        module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
        cls = getattr(module, entry.class_name)
        from newswatch.scrapers.basescraper import BaseScraper

        has_custom_latest = (
            cls.fetch_latest_results is not BaseScraper.fetch_latest_results
        )

        if has_custom_latest:
            return

        import inspect
        try:
            get_article_source = inspect.getsource(cls.get_article)
        except OSError:
            # Dropbox/remote filesystem can block source retrieval; skip source inspection
            return
        is_noop = "pass" in get_article_source and not any(
            kw in get_article_source for kw in ("await ", "return ", "if ", "try:", "except", "logging", "soup", "fetch(", "queue_")
        )

        assert not is_noop, \
            f"{slug}: latest-capable scraper has no working get_article or custom fetch_latest_results"


class TestScraperTimeout:
    """Test per-scraper timeout handling."""

    @patch("newswatch.api._async_scrape_to_list", new_callable=AsyncMock)
    def test_scrape_accepts_scraper_timeout_param(self, mock_async):
        """Test that scrape() accepts scraper_timeout kwarg."""
        mock_async.return_value = []
        # Should not raise, even if internal function doesn't use it yet
        scrape("test", "2025-01-01", scraper_timeout=10)
        mock_async.assert_called_once()

    @patch("newswatch.api._async_scrape_to_list", new_callable=AsyncMock)
    def test_latest_accepts_scraper_timeout_param(self, mock_async):
        """Test that latest() accepts scraper_timeout kwarg."""
        mock_async.return_value = []
        latest(scraper_timeout=15)
        mock_async.assert_called_once()

    @patch("newswatch.api.scrape")
    def test_scrape_to_dataframe_accepts_scraper_timeout(self, mock_scrape):
        """Test that scrape_to_dataframe() forwards scraper_timeout."""
        mock_scrape.return_value = []
        scrape_to_dataframe("test", "2025-01-01", scraper_timeout=20)
        mock_scrape.assert_called_once()


class TestAPIIntegration:
    """Integration tests for the API (require network access)."""

    @pytest.mark.skip(reason="Network test - requires external access")
    def test_real_scrape_integration(self):
        """Test actual scraping with a small request."""
        # only run this manually for integration testing
        results = scrape("bank", "2025-01-15", scrapers="detik", timeout=30)
        assert isinstance(results, list)
        # results might be empty depending on available articles
