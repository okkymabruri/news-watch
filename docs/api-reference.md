# API Reference

The synchronous public API is exported from `newswatch`. Search functions return the eight-field article schema: `title`, `publish_date`, `author`, `content`, `keyword`, `category`, `source`, and `link`.

## Search and retrieval

### `scrape`

```python
scrape(
    keywords=None,
    start_date=None,
    scrapers="auto",
    verbose=False,
    timeout=300,
    method="search",
    limit=None,
    max_pages=None,
    *,
    scraper_timeout=None,
    time_range=None,
    dedup_file=None,
    proxy=None,
    **kwargs,
) -> list[dict]
```

- `keywords`: comma-separated terms; required for search.
- `start_date`: `YYYY-MM-DD`; required for search.
- `scrapers`: `"auto"`, `"all"`, or comma-separated registry slugs.
- `method`: `"search"` or `"latest"`.
- `timeout`: whole operation timeout in seconds.
- `limit`: maximum collected articles; mainly useful for latest mode.
- `max_pages`: latest pages per scraper.
- `scraper_timeout`: timeout for each scraper.
- `time_range`: inclusive date-only window, `START/END` as `YYYY-MM-DD/YYYY-MM-DD` (start 00:00:00, end 23:59:59.999999). This is the Python keyword only — CLI users pass the same value via the canonical `--daterange` flag. The previously deprecated `--time-range` CLI alias was removed in 1.2.0; the Python `time_range=` keyword remains supported and is distinct from that removed flag.
- `dedup_file`: prior CSV, JSON, or JSONL output whose links should be skipped.
- `proxy`: proxy URL used by HTTP and browser request layers.

```python
import newswatch as nw

articles = nw.scrape(
    keywords="ihsg,saham",
    start_date="2026-07-01",
    scrapers="cnbcindonesia,kontan",
)
```

### `scrape_to_dataframe`

Same retrieval parameters as `scrape`; returns a pandas DataFrame. `publish_date` is converted with `pandas.to_datetime(errors="coerce")`.

```python
df = nw.scrape_to_dataframe(
    "ihsg,saham",
    "2026-07-01",
    scrapers="cnbcindonesia,kontan",
)
```

### `scrape_to_file`

```python
scrape_to_file(
    keywords,
    start_date,
    output_path,
    output_format="xlsx",
    scrapers="auto",
    verbose=False,
    timeout=300,
    method="search",
    limit=None,
    max_pages=None,
    *,
    scraper_timeout=None,
    time_range=None,
    dedup_file=None,
    proxy=None,
    **kwargs,
) -> None
```

Supported formats: `xlsx`, `csv`, `json`, and `jsonl`. The Python function defaults to XLSX; the CLI defaults to CSV.

```python
nw.scrape_to_file(
    "ihsg",
    "2026-07-01",
    "ihsg.jsonl",
    output_format="jsonl",
    scrapers="kompas,kontan",
)
```

## Latest convenience functions

```python
latest(
    scrapers="auto", verbose=False, timeout=300,
    limit=None, max_pages=None, *, scraper_timeout=None,
    time_range=None, dedup_file=None, proxy=None,
) -> list[dict]

latest_to_dataframe(
    scrapers="auto", verbose=False, timeout=300,
    limit=None, max_pages=None, *, scraper_timeout=None,
    time_range=None, dedup_file=None, proxy=None,
) -> pandas.DataFrame

latest_to_file(
    output_path, output_format="xlsx", scrapers="auto",
    verbose=False, timeout=300, limit=None, max_pages=None,
    *, scraper_timeout=None, time_range=None,
    dedup_file=None, proxy=None,
) -> None
```

```python
latest = nw.latest_to_dataframe(
    scrapers="antaranews,kompas,viva",
    limit=20,
    scraper_timeout=30,
)
```

## Discovery

### `list_scrapers`

```python
list_scrapers(method="search") -> list[str]
```

Returns the registry slugs that support the selected method.

```python
search_sources = nw.list_scrapers()
latest_sources = nw.list_scrapers(method="latest")
```

The registry is also public:

```python
from newswatch import SCRAPERS, get_scraper_by_slug, get_stable_slugs

entry = get_scraper_by_slug("kompas")
print(entry.supports_search, entry.supports_latest)
```

## Quick search

```python
quick_scrape(keywords, days_back=1, scrapers="auto", *, proxy=None) -> pandas.DataFrame
```

The start date is calculated from the local current date.

```python
recent = nw.quick_scrape("politik,pemerintah", days_back=3)
```

## Health reporting

The stable API includes:

- `health_report`
- `health_report_to_dataframe`
- `health_report_to_file`

Health probes are advisory source checks; they do not replace deterministic tests. See the [Practical Guide](practical-guide.md) for usage.

## Errors

Input errors raise `ValidationError`. Other package-level failures raise `NewsWatchError`.

```python
import newswatch as nw
from newswatch.exceptions import NewsWatchError, ValidationError

try:
    df = nw.scrape_to_dataframe("ihsg", "not-a-date")
except ValidationError as exc:
    print(f"invalid input: {exc}")
except NewsWatchError as exc:
    print(f"collection failed: {exc}")
```

<!-- BEGIN GENERATED: api-notes -->
## Stable API Notes

All 78 registered scrapers are exposed via `list_scrapers()` and the public `SCRAPERS` mapping. 73 of them support the `search` method; all 78 support `latest`.

## Notes

- Prefer `scrapers="auto"` unless you know which sites you need.
- Cloud/server environments are more likely to be blocked.
- Stable support currently covers 76 scrapers (71 search-capable, 76 latest-capable).
- 1 source under investigation; 1 source quarantined.

**Empty results**: Check if your keywords are in Indonesian or try broader terms.
<!-- END GENERATED: api-notes -->
