"""
Tests for the synchronous API module.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from newswatch.api import (
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
        expected_scrapers = ["detik", "kompas", "tempo"]
        for scraper in expected_scrapers:
            assert scraper in scrapers


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


class TestAPIIntegration:
    """Integration tests for the API (require network access)."""

    @pytest.mark.skip(reason="Network test - requires external access")
    def test_real_scrape_integration(self):
        """Test actual scraping with a small request."""
        # only run this manually for integration testing
        results = scrape("bank", "2025-01-15", scrapers="detik", timeout=30)
        assert isinstance(results, list)
        # results might be empty depending on available articles
