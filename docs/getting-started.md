# Getting Started

`news-watch` supports Python 3.10 through 3.12. It provides keyword/date search and latest-news collection through the CLI and Python API.

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install news-watch
```

Browser-backed sources also require Chromium:

```bash
playwright install chromium
```

For repository development:

```bash
git clone https://github.com/okkymabruri/news-watch.git
cd news-watch
uv sync --all-extras
uv run newswatch --list_scrapers
```

## Verify

```bash
newswatch --help
newswatch --list_scrapers
newswatch --method latest --list_scrapers
```

The current registry contains 77 sources: 72 support search and all 77 support latest mode.

## Search by topic and date

```bash
newswatch \
  --method search \
  --keywords "ihsg,saham" \
  --start_date "2025-01-01" \
  --scrapers "cnbcindonesia,kontan,kompas" \
  --output_format csv \
  --output_path ihsg-news.csv
```

Search mode requires keywords and a start date. The CLI defaults to CSV when `--output_format` is omitted.

## Collect latest articles

```bash
newswatch \
  --method latest \
  --scrapers "antaranews,kompas,viva" \
  --limit 20 \
  --output_path latest.csv
```

Latest mode ignores keywords and the search start date.

## Python API

```python
import newswatch as nw

search = nw.scrape_to_dataframe(
    keywords="ihsg,saham",
    start_date="2025-01-01",
    scrapers="cnbcindonesia,kontan,kompas",
)

latest = nw.latest_to_dataframe(
    scrapers="antaranews,kompas,viva",
    limit=20,
)
```

Every article contains eight output fields:

| Field | Meaning |
|---|---|
| `title` | Headline |
| `publish_date` | Publication date and time |
| `author` | Author when available |
| `content` | Extracted article text |
| `keyword` | Search term that matched |
| `category` | Source section or category |
| `source` | Registry slug |
| `link` | Canonical article URL |

## Reliability controls

Start with a few sources and a short date window. Expand only after checking output quality.

```bash
newswatch \
  --keywords "ekonomi" \
  --start_date "2026-07-01" \
  --scrapers "kompas,antaranews" \
  --scraper-timeout 60 \
  --progress
```

Cloud and shared IPs are blocked more often than local connections. See [Troubleshooting](troubleshooting.md) for proxies and source-level diagnosis.

## Next

- [Practical Guide](practical-guide.md): retrieval patterns and reliability controls
- [Use Case MBG](use-case-mbg.md): a real policy-news collection and analysis workflow
- [API Reference](api-reference.md): public functions and parameters
- [Architecture](architecture.md): registry and scraper lifecycle
