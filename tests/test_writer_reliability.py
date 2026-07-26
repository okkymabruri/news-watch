"""Writer cancellation must promote whatever was collected, loudly, instead
of silently losing it (D4: main.py's post-scraping drain can cancel a writer
mid-run on a large backlog)."""

import asyncio
import csv
import json
import logging

import pytest

from newswatch.main import write_csv, write_json, write_jsonl, write_xlsx

_ROW = {
    "title": "t",
    "publish_date": "2026-01-17 00:00:00",
    "author": "a",
    "content": "c",
    "keyword": "k",
    "category": "cat",
    "source": "s",
    "link": "https://example.com",
}


async def _cancel_after_consuming(task, queue, expected_items):
    # Let the writer drain what's already queued, then cancel it while it's
    # blocked waiting for the next (never-arriving) item -- this reproduces
    # main.py cancelling the writer mid-drain.
    for _ in range(50):
        await asyncio.sleep(0.01)
        if queue.empty():
            break
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_write_csv_promotes_partial_output_on_cancellation(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(_ROW)
    await queue.put(_ROW)

    out_path = tmp_path / "out.csv"
    task = asyncio.create_task(write_csv(queue, output_label="test", filename=str(out_path)))
    await _cancel_after_consuming(task, queue, 2)

    assert out_path.exists()
    with open(out_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert "partial output (2 items)" in caplog.text


async def test_write_jsonl_promotes_partial_output_on_cancellation(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(_ROW)

    out_path = tmp_path / "out.jsonl"
    task = asyncio.create_task(write_jsonl(queue, output_label="test", filename=str(out_path)))
    await _cancel_after_consuming(task, queue, 1)

    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["title"] == "t"
    assert "partial output (1 items)" in caplog.text


async def test_write_json_promotes_partial_output_on_cancellation(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(_ROW)
    await queue.put(_ROW)

    out_path = tmp_path / "out.json"
    task = asyncio.create_task(write_json(queue, output_label="test", filename=str(out_path)))
    await _cancel_after_consuming(task, queue, 2)

    assert out_path.exists()
    articles = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(articles) == 2
    assert "partial output (2 items)" in caplog.text


async def test_write_xlsx_promotes_partial_output_on_cancellation(tmp_path, caplog):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    caplog.set_level(logging.WARNING)
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(_ROW)

    out_path = tmp_path / "out.xlsx"
    task = asyncio.create_task(write_xlsx(queue, output_label="test", filename=str(out_path)))
    await _cancel_after_consuming(task, queue, 1)

    assert out_path.exists()
    df = pd.read_excel(out_path)
    assert len(df) == 1
    assert "partial output (1 items)" in caplog.text


async def test_write_csv_cancelled_before_any_item_creates_no_file(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    queue: asyncio.Queue = asyncio.Queue()

    out_path = tmp_path / "out.csv"
    task = asyncio.create_task(write_csv(queue, output_label="test", filename=str(out_path)))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not out_path.exists()
    assert "before any items were written" in caplog.text
