# news-watch Practical Guide

A short, end-to-end walkthrough of `news-watch` covering both retrieval methods and common research and monitoring patterns. For exhaustive function signatures, see the [API Reference](api-reference.md). For installation, see [Getting Started](getting-started.md). For the MBG research workflow, see the [MBG use case guide](mbg-use-case.md).

## Retrieval methods

| Method | When to use | Keywords | Date |
|---|---|---|---|
| `search` (default) | Topic and date research | required | required start (`YYYY-MM-DD`) |
| `latest` | Newest-headlines monitoring | optional | ignored |

Select the method with `--method` on the CLI or `method=` on the Python API. `keywords` and `start_date` are accepted as positional or keyword arguments; `start_date` defaults to today on the CLI when omitted.

## CLI first run

```bash
newswatch --keywords ihsg --start_date 2025-01-01
newswatch --method latest --scrapers "antaranews,kompas,viva"
```

Defaults: `--output_format csv`, `--scrapers auto`, `--verbose` off, `--method search`. The file lands in the working directory as `news-watch-{keywords}-YYYYMMDD_HH.csv`. Override with `--output_path` / `-o`.

For browser-backed scrapers (Bisnis, IDN Times, Liputan6, Pikiran Rakyat, Republika, Suara, Tirto, The Jakarta Post), install Playwright once:

```bash
playwright install chromium
```

## Python API first run

```python
import newswatch as nw

df = nw.scrape_to_dataframe("ihsg", "2025-01-01")
print(len(df), df["source"].value_counts().head())

latest = nw.latest_to_dataframe(scrapers="antaranews,kompas,viva")
print(latest[["source", "title"]].head())
```

The public surface follows [SemVer](https://semver.org/) from 1.0 onward: `scrape`, `scrape_to_dataframe`, `scrape_to_file`, `quick_scrape`, `latest`, `latest_to_dataframe`, `latest_to_file`, `list_scrapers`, `SCRAPERS`, `get_scraper_by_slug`, `get_stable_slugs`, `get_stable_scrapers`, `health_report`, `health_report_to_dataframe`, `health_report_to_file`.

Output schema (8 fields): `title`, `publish_date`, `author`, `content`, `keyword`, `category`, `source`, `link`. `publish_date` is auto-parsed on `scrape_to_dataframe`; the internal `Article.scrape_timestamp` is **not** written to output.

## Choosing sources

```python
nw.list_scrapers()                # all sources
nw.list_scrapers(method="latest") # sources that support latest mode
```

- `"auto"` — let `news-watch` pick platform-appropriate sources.
- `"all"` — force every source; can fail on servers.
- `"kompas,tempo"` — comma-separated slugs.

For larger sweeps, narrow the date window or `--limit` to bound cost; for noisy periods, narrow `--scrapers` before retrying.

<!-- BEGIN GENERATED: guide-counts -->
The stable release currently exposes 70 supported scrapers. No investigating or quarantined sources remain.

70 of 70 sources support latest monitoring.
<!-- END GENERATED: guide-counts -->

## Saving results

```python
nw.scrape_to_file("ekonomi", "2025-01-01", "economic_news.xlsx")
nw.scrape_to_file("startup", "2025-01-01", "startup_news.csv", output_format="csv", scrapers="tempo,kompas")
nw.scrape_to_file("fintech", "2025-01-01", "fintech.json", output_format="json", scrapers="tempo,kompas")
nw.latest_to_file("latest.json", output_format="json", scrapers="antaranews,kompas")
```

Formats: `csv` (default on CLI), `xlsx`, `json`, `jsonl`. On the Python API, `scrape_to_file` defaults to `xlsx`.

## Common patterns

### Latest-monitoring sweep

```python
import newswatch as nw

df = nw.latest_to_dataframe(
    scrapers="antaranews,kompas,viva",
    limit=50,
    scraper_timeout=30,
)
print(df.groupby("source").size())
```

### Date-windowed keyword search

```python
import newswatch as nw

df = nw.scrape_to_dataframe(
    keywords="ihsg,saham,obligasi",
    start_date="2025-01-01",
    time_range="2025-01-01T00:00:00/2025-01-31T23:59:59",
    scrapers="cnbcindonesia,kontan,bisnis",
    verbose=True,
)
```

### Dedup against a previous run

```bash
newswatch --keywords ihsg --start_date 2025-01-01 --dedup-file previous-output.csv
```

### Proxy and reliability knobs

```bash
export NEWSWATCH_PROXY="socks5://proxy.example.com:1080"
export NEWSWATCH_USER_AGENT="Mozilla/5.0 ..."
export NEWSWATCH_MAX_RETRIES=3
newswatch --keywords ihsg --start_date 2025-01-01
```

All knobs also work as keyword arguments (`proxy=`, `scraper_timeout=`) or CLI flags.

## Reliability and limits

- **Local runs are most reliable.** Cloud and shared IPs get blocked more often; route through `--proxy` when running on Colab or CI.
- **Strict-search policy** — sources with `Yes` in the Search column of [index.md](index.md) have verified keyword workflows; a non-empty result for a nonsense keyword is a bug, not a feature.
- **AP News** uses topic hub pages with keyword-in-title filtering (no `/search?q=`); **Al Jazeera** is latest-only via RSS.
- **Output defaults:** CLI writes CSV in the working directory; `scrape_to_file` defaults to XLSX. Honor both, or pass `output_format` explicitly.
- **Quarantined / investigating sources** are excluded from the runtime; the registry is the source of truth.

## Next steps

- [API Reference](api-reference.md) — function signatures and parameters.
- [Architecture](architecture.md) — registry, scraper states, validation gate.
- [Troubleshooting](troubleshooting.md) — install, runtime, and platform notes.
- [MBG use case](mbg-use-case.md) — end-to-end MBG research workflow with quality gates.
