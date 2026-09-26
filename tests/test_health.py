"""Tests for the health report module."""

import csv
import json
import asyncio
import logging
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from newswatch.health import (
    append_health_history,
    health_report,
    health_report_to_dataframe,
    health_report_to_file,
    _print_health_summary,
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

    @pytest.mark.parametrize(
        ("failure", "expected", "count"),
        [
            (None, "ok", 1),
            ("empty", "no_results", 0),
            ("error", "partial_error", 1),
            ("timeout", "partial_timeout", 1),
            ("error_empty", "error", 0),
            ("timeout_empty", "timeout", 0),
        ],
    )
    def test_queue_and_terminal_outcome(self, failure, expected, count, tmp_path, capsys):
        class QueueScraper:
            def __init__(self, keywords, queue_, **kwargs):
                self.queue_ = queue_
                self._articles_collected = 0

            async def scrape(self, method):
                if failure not in ("empty", "error_empty", "timeout_empty"):
                    await self.queue_.put({"title": "queued"})
                    self._articles_collected = 1
                if failure in ("error", "error_empty"):
                    raise ValueError("probe failed")
                if failure in ("timeout", "timeout_empty"):
                    await asyncio.sleep(1)

        with patch("newswatch.health.get_available_scrapers", return_value={
            "kompas": {"class": QueueScraper, "params": {}}
        }):
            record = health_report(scrapers="kompas", scraper_timeout=0.001, limit=1)[0]
        assert record["status"] == expected
        assert record["article_count"] == count
        assert record["error_type"] == (
            "TimeoutError" if "timeout" in expected else "ValueError" if "error" in expected else None
        )
        assert bool(record["error_message"]) == ("error" in expected or "timeout" in expected)
        _print_health_summary([record])
        assert expected in capsys.readouterr().out
        path = tmp_path / "history.jsonl"
        append_health_history([record], path)
        assert json.loads(path.read_text())["status"] == expected

    def test_missing_import_and_constructor_failure_are_per_source(self):
        class BrokenScraper:
            def __init__(self, **kwargs):
                raise RuntimeError("constructor failed")

        class EmptyScraper:
            def __init__(self, keywords, queue_, **kwargs):
                self.queue_ = queue_
                self._articles_collected = 0

            async def scrape(self, method):
                pass

        available = {
            "bbc": {"class": BrokenScraper, "params": {}},
            "kompas": {"class": EmptyScraper, "params": {}},
        }
        with patch("newswatch.health.get_available_scrapers", return_value=available):
            records = health_report(scrapers="antaranews,bbc,kompas,not-a-source")
        assert [r["status"] for r in records] == [
            "error", "error", "no_results", "unsupported"
        ]
        assert records[0]["error_type"] == "ImportError"
        assert records[1]["error_message"] == "constructor failed"

    def test_auto_includes_eligible_import_failure(self):
        with patch("newswatch.health.get_available_scrapers", return_value={}):
            records = health_report(method="search", scrapers="auto")
        by_slug = {record["slug"]: record for record in records}
        assert by_slug["antaranews"]["status"] == "error"
        assert by_slug["antaranews"]["error_type"] == "ImportError"
        assert "hukumonline" not in by_slug  # latest-only

    def test_restores_callers_logging_disable_level(self):
        previous = logging.root.manager.disable
        try:
            logging.disable(logging.ERROR)
            with patch("newswatch.health.get_available_scrapers", return_value={}):
                health_report(scrapers="not-a-source")
            assert logging.root.manager.disable == logging.ERROR
        finally:
            logging.disable(previous)

    def test_health_report_exposes_search_error(self):
        from newswatch.scrapers.basescraper import BaseScraper

        class FailingSearchScraper(BaseScraper):
            async def build_search_url(self, keyword, page):
                return None

            def parse_article_links(self, response_text):
                return []

            async def get_article(self, link, keyword):
                return None

            async def fetch_search_results(self, keyword):
                raise ValueError("keyword failed")

        available = {
            "cnbcindonesia": {"class": FailingSearchScraper, "params": {}}
        }
        with patch("newswatch.health.get_available_scrapers", return_value=available):
            result = health_report(
                method="search", scrapers="cnbcindonesia", scraper_timeout=0
            )

        assert result[0]["status"] == "error"
        assert result[0]["error_type"] == "ValueError"
        assert result[0]["error_message"] == "keyword failed"


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

    def test_csv_mixed_rows_preserves_all_fields(self):
        unsupported_row = {"slug": "badslug", "status": "unsupported", "article_count": 0, "elapsed_seconds": 0, "error_type": None, "error_message": "Not available"}
        ok_row = {"slug": "apnews", "status": "ok", "article_count": 1, "elapsed_seconds": 2.1, "error_type": None, "error_message": None, "name": "AP News", "method": "latest"}
        report = [unsupported_row, ok_row]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            health_report_to_file(report, f.name, "csv")
            with open(f.name) as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
            assert len(rows) == 2
            assert rows[0]["slug"] == "badslug"
            assert rows[1]["slug"] == "apnews"
            assert "name" in rows[1] and rows[1]["name"] == "AP News"
            Path(f.name).unlink()

    def test_xlsx_output(self):
        report = [{"slug": "test", "status": "ok"}]
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            health_report_to_file(report, f.name, "xlsx")
            assert Path(f.name).exists()
            df = pd.read_excel(f.name)
            assert len(df) == 1
            Path(f.name).unlink()

    def test_jsonl_output(self):
        report = [{"slug": "test", "status": "ok"}]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            health_report_to_file(report, f.name, "jsonl")
            with open(f.name) as fh:
                lines = [line.strip() for line in fh if line.strip()]
            assert len(lines) == 1
            assert json.loads(lines[0]) == report[0]
            Path(f.name).unlink()

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Unsupported format"):
            health_report_to_file([], "test.xml", "xml")


class TestPrintHealthSummary:
    """Test stdout summary table."""

    def test_empty_report(self, capsys):
        _print_health_summary([])
        captured = capsys.readouterr()
        assert "No health data." in captured.out

    def test_summary_with_results(self, capsys):
        report = [
            {"slug": "kompas", "status": "ok", "article_count": 5, "elapsed_seconds": 2.3, "error_message": None},
            {"slug": "tempo", "status": "timeout", "article_count": 0, "elapsed_seconds": 30.0, "error_message": "Exceeded 30s timeout"},
            {"slug": "detik", "status": "error", "article_count": 0, "elapsed_seconds": 5.1, "error_message": "Connection failed"},
            {"slug": "bbc", "status": "no_results", "article_count": 0, "elapsed_seconds": 1.2, "error_message": None},
        ]
        _print_health_summary(report)
        captured = capsys.readouterr()
        assert "SOURCE" in captured.out
        assert "kompas" in captured.out
        assert "Summary:" in captured.out
        assert "1/4 OK" in captured.out
        assert "1 timeouts" in captured.out
        assert "1 errors" in captured.out



class TestAppendHealthHistory:
    """Test append-only JSONL health history persistence."""

    def _sample(self):
        return [
            {"slug": "kompas", "status": "ok", "article_count": 3,
             "error_message": None, "error_type": None,
             "method": "latest", "elapsed_seconds": 1.5, "name": "Kompas"},
            {"slug": "tempo", "status": "timeout", "article_count": 0,
             "error_message": "Exceeded 30s", "error_type": "TimeoutError",
             "method": "latest", "elapsed_seconds": 30.0, "name": "Tempo"},
        ]

    def test_empty_report_returns_zero(self, tmp_path):
        path = tmp_path / "h.jsonl"
        assert append_health_history([], path) == 0
        # The function may create the parent dir as a side effect;
        # what we care about is that no file is written and count is zero.
        assert not path.exists() or path.stat().st_size == 0
        path = tmp_path / "h.jsonl"
        n = append_health_history(self._sample(), path, run_id="r1", timestamp="2026-07-06T00:00:00")
        assert n == 2
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        rec1 = json.loads(lines[0])
        assert rec1["run_id"] == "r1"
        assert rec1["timestamp"] == "2026-07-06T00:00:00"
        assert rec1["source"] == "kompas"
        assert rec1["status"] == "ok"
        assert rec1["count"] == 3
        assert rec1["method"] == "latest"
        assert rec1["name"] == "Kompas"
        rec2 = json.loads(lines[1])
        assert rec2["source"] == "tempo"
        assert rec2["error_type"] == "TimeoutError"

    def test_run_id_and_timestamp_default_stable_across_records(self, tmp_path):
        path = tmp_path / "h.jsonl"
        append_health_history(self._sample(), path)
        lines = path.read_text(encoding="utf-8").splitlines()
        r1, r2 = (json.loads(line) for line in lines)
        assert r1["run_id"] == r2["run_id"]
        assert r1["timestamp"] == r2["timestamp"]
        # generated run_id is 8 hex chars
        assert len(r1["run_id"]) == 8
        int(r1["run_id"], 16)  # raises if not hex

    def test_corrupt_record_skipped_other_records_persisted(self, tmp_path):
        path = tmp_path / "h.jsonl"
        bad = {"slug": "x", "status": "ok", "error_message": object()}  # unserializable
        good = self._sample()
        n = append_health_history([bad, *good, bad], path, run_id="r2")
        assert n == 2  # only the 2 good records
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert all(json.loads(line)["run_id"] == "r2" for line in lines)

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "deeper" / "h.jsonl"
        n = append_health_history(self._sample(), path)
        assert n == 2
        assert path.exists()

    def test_appends_to_existing_file(self, tmp_path):
        path = tmp_path / "h.jsonl"
        append_health_history(self._sample()[:1], path, run_id="r1")
        append_health_history(self._sample()[1:], path, run_id="r2")
        lines = path.read_text(encoding="utf-8").splitlines()
        runs = {json.loads(line)["run_id"] for line in lines}
        assert runs == {"r1", "r2"}

