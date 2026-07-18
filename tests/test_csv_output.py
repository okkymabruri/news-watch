import asyncio
import csv

from newswatch.main import write_csv


async def test_write_csv_roundtrip_preserves_embedded_specials(tmp_path):
    row = {
        "title": "t",
        "publish_date": "2026-01-17 00:00:00",
        "author": "a",
        "content": 'line1\nline2, with comma and a "quote"',
        "keyword": "k",
        "category": "c",
        "source": "s",
        "link": "https://example.com",
    }
    expected_fieldnames = [
        "title",
        "publish_date",
        "author",
        "content",
        "keyword",
        "category",
        "source",
        "link",
    ]

    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(row)
    await queue.put(None)

    out_path = tmp_path / "out.csv"
    await write_csv(queue, output_label="test", filename=str(out_path))

    with open(out_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == expected_fieldnames
        rows = list(reader)

    assert len(rows) == 1
    parsed = rows[0]
    for key in expected_fieldnames:
        assert parsed[key] == row[key]