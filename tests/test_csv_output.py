import csv

import pandas as pd


def test_csv_roundtrip_quotes_newlines(tmp_path):
    path = tmp_path / "out.csv"
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

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(row.keys()),
            quoting=csv.QUOTE_ALL,
        )
        w.writeheader()
        w.writerow(row)

    df = pd.read_csv(path)
    assert list(df.columns) == list(row.keys())
    assert df.loc[0, "content"] == row["content"]
