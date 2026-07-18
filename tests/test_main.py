import logging
from argparse import Namespace
from datetime import datetime

import pytest

from newswatch.main import _parse_time_range, main


@pytest.mark.asyncio
async def test_main_no_scrapers(caplog):
    caplog.set_level(logging.ERROR)
    args = Namespace(
        keywords="test", start_date="2023-10-01", scrapers="invalid_scraper", verbose=0
    )
    await main(args)
    assert "no valid scrapers selected. exiting." in caplog.text

def test_parse_time_range_multi_day_inclusive():
    """multi-day date-only range expands start to local midnight and end to 23:59:59.999999."""
    start, end = _parse_time_range("2026-07-13/2026-07-15")
    assert start == datetime(2026, 7, 13, 0, 0, 0, 0)
    assert end == datetime(2026, 7, 15, 23, 59, 59, 999999)

def test_parse_time_range_same_day():
    """same-day window expands to a full local day from midnight to 23:59:59.999999."""
    start, end = _parse_time_range("2026-07-13/2026-07-13")
    assert start == datetime(2026, 7, 13, 0, 0, 0, 0)
    assert end == datetime(2026, 7, 13, 23, 59, 59, 999999)

def test_parse_time_range_rejects_datetime_input():
    """datetime-bearing inputs (with 'T' separator) are rejected."""
    with pytest.raises(ValueError):
        _parse_time_range("2026-07-13T10:00:00/2026-07-14T10:00:00")

@pytest.mark.parametrize(
    "bad_input",
    [
        "not-a-date/2026-07-14",
        "2026-13-01/2026-07-14",
        "2026-07-13/2026-02-30",
    ],
)
def test_parse_time_range_rejects_invalid_dates(bad_input):
    """non-date and out-of-range date strings are rejected."""
    with pytest.raises(ValueError):
        _parse_time_range(bad_input)

@pytest.mark.parametrize(
    "bad_input",
    [
        "2026-07-13",
        "2026-07-13/2026-07-14/extra",
    ],
)
def test_parse_time_range_rejects_malformed_format(bad_input):
    """strings without exactly one '/' separator are rejected."""
    with pytest.raises(ValueError):
        _parse_time_range(bad_input)

def test_parse_time_range_rejects_reversed_bounds():
    """start date after end date is rejected."""
    with pytest.raises(ValueError):
        _parse_time_range("2026-07-15/2026-07-13")
