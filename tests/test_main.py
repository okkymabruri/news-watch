import asyncio
import logging
from argparse import Namespace
from datetime import datetime
from types import SimpleNamespace

import pytest

from newswatch import main as main_module
from newswatch.main import _compute_outer_timeout, _parse_time_range, main


@pytest.mark.asyncio
async def test_main_no_scrapers(caplog):
    caplog.set_level(logging.ERROR)
    args = Namespace(
        keywords="test", start_date="2023-10-01", scrapers="invalid_scraper", verbose=0
    )
    await main(args)
    assert "no valid scrapers selected. exiting." in caplog.text


def _make_tracking_scraper_class():
    """A fake scraper class whose scrape() records peak concurrency of
    instances of THIS class -- a fresh class per test group keeps browser
    vs. general pool counts independent."""

    class _Tracking:
        active = 0
        max_active = 0

        def __init__(self, keywords, start_date=None, queue_=None, **kwargs):
            self.queue_ = queue_

        async def scrape(self, method="search"):
            cls = type(self)
            cls.active += 1
            cls.max_active = max(cls.max_active, cls.active)
            await asyncio.sleep(0.05)
            cls.active -= 1

    return _Tracking


@pytest.mark.asyncio
async def test_max_concurrent_scrapers_caps_general_pool(tmp_path, monkeypatch):
    General = _make_tracking_scraper_class()
    scraper_classes = {
        f"general{i}": {"class": General, "params": {}} for i in range(8)
    }

    monkeypatch.setattr(
        main_module, "get_available_scrapers", lambda method="search": scraper_classes
    )
    monkeypatch.setattr(
        main_module,
        "get_scraper_by_slug",
        lambda slug: SimpleNamespace(browser_required=False),
    )

    args = Namespace(
        keywords="test",
        start_date=None,
        scrapers="all",
        output_path=str(tmp_path / "out.csv"),
        output_format="csv",
        max_concurrent_scrapers=3,
    )
    await main(args)

    assert General.max_active <= 3


@pytest.mark.asyncio
async def test_browser_required_scrapers_share_smaller_pool(tmp_path, monkeypatch):
    General = _make_tracking_scraper_class()
    Browser = _make_tracking_scraper_class()
    scraper_classes = {
        **{f"general{i}": {"class": General, "params": {}} for i in range(6)},
        **{f"browser{i}": {"class": Browser, "params": {}} for i in range(6)},
    }

    monkeypatch.setattr(
        main_module, "get_available_scrapers", lambda method="search": scraper_classes
    )
    monkeypatch.setattr(
        main_module,
        "get_scraper_by_slug",
        lambda slug: SimpleNamespace(browser_required=slug.startswith("browser")),
    )

    args = Namespace(
        keywords="test",
        start_date=None,
        scrapers="all",
        output_path=str(tmp_path / "out.csv"),
        output_format="csv",
        max_concurrent_scrapers=6,
    )
    await main(args)

    # Browser pool is capped at min(2, max_concurrent_scrapers) regardless of
    # the general pool's larger cap (issue #47: Chromium launches are far
    # heavier than a plain HTTP request and must not share the general pool).
    assert Browser.max_active <= 2
    assert General.max_active <= 6


def test_compute_outer_timeout_scales_with_wave_count():
    entries = [(f"s{i}", None) for i in range(12)]
    # 12 scrapers, cap 3 -> 4 waves; scraper_timeout 100 -> 4*100+60
    assert _compute_outer_timeout(entries, 3, 100) == 460


def test_compute_outer_timeout_uses_180_default_when_no_scraper_timeout():
    entries = [(f"s{i}", None) for i in range(3)]
    # 3 scrapers, cap 3 -> 1 wave; no scraper_timeout -> falls back to 180
    assert _compute_outer_timeout(entries, 3, None) == 240


def test_compute_outer_timeout_never_below_one_wave_with_no_scrapers():
    assert _compute_outer_timeout([], 6, 100) == 160

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
