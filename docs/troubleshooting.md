# Troubleshooting

Reduce a failing run to one source, one broad keyword, and a recent date before changing code.

## No results

```bash
newswatch \
  --keywords "indonesia" \
  --start_date "2026-07-01" \
  --scrapers kompas \
  --verbose
```

Check:

1. The source supports search: `newswatch --method search --list_scrapers`.
2. The keyword appears in Indonesian coverage.
3. The requested date is within the source's exposed search history.
4. The source is not returning a block page or empty search result.

All 77 sources support latest mode, but five are latest-only.

## Timeout or access block

Run fewer sources and set an explicit per-source timeout:

```bash
newswatch \
  --keywords "politik" \
  --start_date "2026-07-01" \
  --scrapers "kompas,tempo" \
  --scraper-timeout 60 \
  --progress
```

Cloud, CI, and shared IP addresses are blocked more often. Configure one proxy for all HTTP and browser layers:

```bash
newswatch --keywords ihsg --start_date 2026-07-01 \
  --proxy "http://proxy.example.com:8080"

export NEWSWATCH_PROXY="socks5://proxy.example.com:1080"
```

Python:

```python
import newswatch as nw

result = nw.scrape_to_dataframe(
    "ihsg",
    "2026-07-01",
    scrapers="kompas",
    proxy="http://proxy.example.com:8080",
)
```

Optional environment controls:

- `NEWSWATCH_USER_AGENT`: custom user agent
- `NEWSWATCH_MAX_RETRIES`: request retry limit; default 3

## Browser-backed source fails

Install the browser once in the active environment:

```bash
playwright install chromium
```

On Linux, Playwright can install system packages when permitted:

```bash
playwright install-deps chromium
```

If browser installation is unavailable, select HTTP-only sources instead.

## Missing or truncated content

Possible causes: a changed page structure, paywall, block page, or source response without a full body.

Inspect one source with verbose output and preserve an example URL when reporting the problem:

```bash
newswatch --keywords ekonomi --start_date 2026-07-01 \
  --scrapers kompas --verbose
```

Do not replace missing bodies with fabricated text. Empty extraction should remain visible.

## Duplicates

Multiple keywords and publishers can return the same URL or syndicated headline. Use `--dedup-file` across runs, then apply documented URL and normalized-title rules during analysis.

```bash
newswatch --keywords ihsg --start_date 2026-07-01 \
  --dedup-file previous-output.csv
```

## Command not found or import failure

Installed package:

```bash
python -m pip show news-watch
python -c "import newswatch; print(newswatch.__file__)"
```

Repository checkout:

```bash
uv sync --all-extras
uv run newswatch --help
```

## Tests

```bash
uv run --extra dev pytest -m "not network"
uv run --extra dev pytest tests/test_scrapers.py -m network
```

Network tests are advisory. Known upstream failures may skip; parser and programming defects must fail.

## Report a bug

Include:

- OS and Python version
- exact command
- full error output
- source slug
- one example URL, if applicable
- whether the failure reproduces locally and from another network
