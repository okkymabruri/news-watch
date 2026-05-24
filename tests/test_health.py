"""Tests for the health report module."""

import asyncio
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from newswatch.health import (
    health_report,
    health_report_to_dataframe,
    health_report_to_file,
    print_health_summary,
)


class TestHealthReportAPI:
    """Test health_report sync API."""

    @patch("newswatch.health._async_health_report", new_callable=AsyncMock)
    def test_health_report_returns_list(self, mock_async):
        mock_async.return_value = [{"slug": "kompas", "status": "ok"}]
        result = health_report(scrapers="kompas")
        assert isinstance(result, list)
        assert len(result) == 1

    @patch("newswatch.health._async_health_report", new_callable=AsyncMock)
    def test_health_report_empty_on_error(self, mock_async):
        mock_async.side_effect = RuntimeError("fail")
        result = health_report(scrapers="kompas")
        assert result == []


class TestHealthReportToDataFrame:
    """Test DataFrame conversion."""

    def test_empty_report(self):
        df = health_report_to_dataframe([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_report_to_dataframe(self):
        report = [
            {"slug": "kompas", "status": "ok", "article_count": 3},
            {"slug": "tempo", "status": "timeout", "article_count": 0},
        ]
        df = health_report_to_dataframe(report)
        assert len(df) == 2
        assert "slug" in df.columns
        assert "status" in df.columns


class TestHealthReportToFile:
    """Test file output."""

    def test_json_output(self):
        report = [{"slug": "test", "status": "ok"}]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            health_report_to_file(report, f.name, "json")
            with open(f.name) as fh:
                data = json.load(fh)
            assert data == report
            Path(f.name).unlink()

    def test_csv_output(self):
        report = [{"slug": "test", "status": "ok"}]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            health_report_to_file(report, f.name, "csv")
            with open(f.name) as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["slug"] == "test"
            Path(f.name).unlink()

    def test_csv_empty_report(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            health_report_to_file([], f.name, "csv")
            assert Path(f.name).exists()
            Path(f.name).unlink()

    def test_xlsx_output(self):
        report = [{"slug": "test", "status": "ok"}]
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            health_report_to_file(report, f.name, "xlsx")
            assert Path(f.name).exists()
            df = pd.read_excel(f.name)
            assert len(df) == 1
            Path(f.name).unlink()

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Unsupported format"):
            health_report_to_file([], "test.xml", "xml")


class TestPrintHealthSummary:
    """Test stdout summary table."""

    def test_empty_report(self, capsys):
        print_health_summary([])
        captured = capsys.readouterr()
        assert "No health data." in captured.out

    def test_summary_with_results(self, capsys):
        report = [
            {"slug": "kompas", "status": "ok", "article_count": 5, "elapsed_seconds": 2.3, "error_message": None},
            {"slug": "tempo", "status": "timeout", "article_count": 0, "elapsed_seconds": 30.0, "error_message": "Exceeded 30s timeout"},
            {"slug": "detik", "status": "error", "article_count": 0, "elapsed_seconds": 5.1, "error_message": "Connection failed"},
            {"slug": "bbc", "status": "no_results", "article_count": 0, "elapsed_seconds": 1.2, "error_message": None},
        ]
        print_health_summary(report)
        captured = capsys.readouterr()
        assert "SOURCE" in captured.out
        assert "kompas" in captured.out
        assert "Summary:" in captured.out
        assert "1/4 OK" in captured.out
        assert "1 timeouts" in captured.out
        assert "1 errors" in captured.out
