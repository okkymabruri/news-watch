"""Contracts for the single-clock convention.

Every source's publish_date has to land on one clock. Before this, an offset
was discarded rather than converted, so a -04:00 article and a +07:00 article
published 11 hours apart got identical timestamps -- and the writers' range
filter compared aware against naive and died. These pin both halves.
"""

import asyncio
import csv
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from newswatch.main import _in_time_range, _parse_time_range, write_csv, write_json, write_jsonl, write_xlsx
from newswatch.scrapers.basescraper import BaseScraper
from newswatch.timeutils import project_timezone, to_project_naive


class _Dummy(BaseScraper):
    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return []

    async def get_article(self, link, keyword):
        pass


# ── to_project_naive ─────────────────────────────────────────────────────────


def test_aware_input_is_converted_not_truncated():
    utc_noon = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    result = to_project_naive(utc_noon)
    expected = utc_noon.astimezone(project_timezone()).replace(tzinfo=None)
    assert result == expected
    assert result.tzinfo is None
    # Asia/Jakarta is UTC+7, so truncation (12:00) and conversion differ.
    assert result != utc_noon.replace(tzinfo=None)


def test_naive_input_passes_through_unchanged():
    naive = datetime(2026, 7, 27, 8, 0)
    assert to_project_naive(naive) == naive


def test_assume_tz_reinterprets_naive_input():
    naive = datetime(2026, 7, 27, 8, 0)
    result = to_project_naive(naive, assume_tz=ZoneInfo("America/New_York"))
    assert result != naive
    assert result == naive.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(
        project_timezone()
    ).replace(tzinfo=None)


@pytest.mark.parametrize("value", [None, "not a datetime", 42])
def test_non_datetime_passes_through(value):
    assert to_project_naive(value) is value


def test_same_instant_in_different_zones_collapses_to_one_value():
    """The core guarantee: identical instants, different offsets, one result."""
    et = datetime(2026, 7, 27, 8, 0, tzinfo=timezone(timedelta(hours=-4)))
    wib = datetime(2026, 7, 27, 19, 0, tzinfo=timezone(timedelta(hours=7)))
    assert et == wib  # same instant
    assert to_project_naive(et) == to_project_naive(wib)


def test_different_instants_sharing_a_wall_clock_stay_distinct():
    """The bug this fixes: these used to both become 08:00."""
    et = datetime(2026, 7, 27, 8, 0, tzinfo=timezone(timedelta(hours=-4)))
    wib = datetime(2026, 7, 27, 8, 0, tzinfo=timezone(timedelta(hours=7)))
    assert to_project_naive(et) != to_project_naive(wib)


# ── BaseScraper.parse_date ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "date_string",
    [
        "2026-07-27T08:00:00-04:00",
        "2026-07-27T19:00:00+07:00",
        "2026-07-27T12:00:00Z",
    ],
)
def test_parse_date_maps_equivalent_instants_to_one_value(date_string):
    """All three strings are the same instant, so all three must agree."""
    scraper = _Dummy("ihsg")
    reference = to_project_naive(datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc))
    assert scraper.parse_date(date_string) == reference


def test_parse_date_leaves_offsetless_input_on_its_wall_clock():
    """Indonesian sources publish without an offset; their output must not move."""
    scraper = _Dummy("ihsg")
    parsed = scraper.parse_date("2026-07-27 08:00:00")
    assert parsed == datetime(2026, 7, 27, 8, 0)
    assert parsed.tzinfo is None


def test_parse_date_returns_none_for_garbage():
    assert _Dummy("ihsg").parse_date("not a date at all") is None


# ── _in_time_range ──────────────────────────────────────────────────────────


def test_in_time_range_accepts_offset_bearing_string():
    """Comparing an aware datetime against naive bounds used to raise TypeError."""
    start, end = _parse_time_range("2026-07-27/2026-07-27")
    # 08:00-04:00 is 19:00 in Asia/Jakarta, inside the 27th.
    assert _in_time_range("2026-07-27T08:00:00-04:00", start, end) is True


def test_in_time_range_excludes_out_of_range_offset_string():
    start, end = _parse_time_range("2026-07-27/2026-07-27")
    # 20:00-04:00 is 07:00 on the 28th in Asia/Jakarta -- outside.
    assert _in_time_range("2026-07-27T20:00:00-04:00", start, end) is False


def test_in_time_range_rejects_unparseable_and_non_datetime():
    start, end = _parse_time_range("2026-07-27/2026-07-27")
    assert _in_time_range("garbage", start, end) is False
    assert _in_time_range(12345, start, end) is False


# ── Writers keep producing a file when a timestamp carries an offset ─────────

_AWARE_ITEM = {
    "title": "Offset-bearing timestamp",
    "publish_date": "2026-07-27T08:00:00-04:00",
    "author": "Reporter",
    "content": "Body text for the aware-timestamp writer regression.",
    "keyword": "election",
    "category": "news",
    "source": "abcnews.com",
    "link": "https://abcnews.com/story-1",
}


async def _drive(writer, path):
    queue = asyncio.Queue()
    await queue.put(dict(_AWARE_ITEM))
    await queue.put(None)
    await writer(
        queue,
        "test",
        filename=str(path),
        time_range=_parse_time_range("2026-07-27/2026-07-27"),
    )


@pytest.mark.asyncio
async def test_write_csv_keeps_row_with_aware_timestamp(tmp_path):
    out = tmp_path / "out.csv"
    await _drive(write_csv, out)
    assert out.exists(), "writer died on the aware/naive comparison"
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["link"] == _AWARE_ITEM["link"]


@pytest.mark.asyncio
async def test_write_json_keeps_row_with_aware_timestamp(tmp_path):
    out = tmp_path / "out.json"
    await _drive(write_json, out)
    assert out.exists()
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 1


@pytest.mark.asyncio
async def test_write_jsonl_keeps_row_with_aware_timestamp(tmp_path):
    out = tmp_path / "out.jsonl"
    await _drive(write_jsonl, out)
    assert out.exists()
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1


@pytest.mark.asyncio
async def test_write_xlsx_keeps_row_with_aware_timestamp(tmp_path):
    pd = pytest.importorskip("pandas")
    out = tmp_path / "out.xlsx"
    await _drive(write_xlsx, out)
    assert out.exists()
    assert len(pd.read_excel(out)) == 1


@pytest.mark.asyncio
async def test_api_collector_keeps_row_with_aware_timestamp():
    from newswatch.api import _collect_queue_results

    queue = asyncio.Queue()
    await queue.put(dict(_AWARE_ITEM))
    await queue.put(None)
    done = asyncio.Event()
    done.set()

    results = await _collect_queue_results(
        queue, done, time_range=_parse_time_range("2026-07-27/2026-07-27")
    )
    assert len(results) == 1
    assert results[0]["link"] == _AWARE_ITEM["link"]
