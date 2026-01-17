# Troubleshooting

## Installation

### Playwright

If `playwright install chromium` fails:
```bash
# Install playwright browser for news-watch
conda activate newswatch-env
playwright install chromium

# For system dependencies
playwright install-deps chromium

# For Docker/Linux environments
apt-get update && apt-get install -y \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libxss1 libasound2
```

### Package install

If install/import fails:
```bash
# If uv is not available, fallback to pip
pip install news-watch

# Development setup (recommended)
git clone https://github.com/okkymabruri/news-watch.git
cd news-watch
uv sync --all-extras
uv run playwright install chromium
```

## Runtime

### No results

Quick checks:
```bash
newswatch --list_scrapers
newswatch --keywords indonesia --start_date 2025-01-15 -v
```

Common causes:

- keywords too specific → try `ekonomi,bisnis,indonesia`
- date too old → try a recent date first
- blocked in cloud/Linux → try fewer scrapers or run locally

### Timeout

Try:
```bash
newswatch --keywords politik --start_date 2025-01-01 --scrapers "kompas,detik"
```

### Memory

For large runs, write to a file:
```bash
newswatch --keywords ekonomi --start_date 2024-01-01 --output_format xlsx
```

## Platform notes

### Linux / cloud

Some sites block server/cloud IPs more aggressively.

Try:
```bash
newswatch --keywords berita --start_date 2025-01-01
```

## Data quality

### Missing/truncated content

Causes:

- HTML structure changed
- paywall
- blocked

Check with verbose + single scraper:
```bash
newswatch --keywords ekonomi --start_date 2025-01-01 -v
newswatch --keywords ekonomi --start_date 2025-01-01 --scrapers kompas -v
newswatch --keywords ekonomi --start_date 2025-01-01 --scrapers detik -v
```

### Duplicates

Normal when multiple sites cover the same story. Deduplicate in post-processing.

### Encoding

If text has broken characters, try another source:
```bash
newswatch --keywords berita --start_date 2025-01-01 --scrapers "kompas,tempo" -v
```

## CLI

### Command not found

If `newswatch` is not found:
```bash
conda activate newswatch-env
which newswatch
uv sync --all-extras
```

### Arguments

Check:
```bash
newswatch --help
```

## Tests

### Running tests

```bash
pytest tests/
pytest -m network
pytest -m "not network"
```

## Reporting bugs

Include:

- OS + Python version
- command you ran
- full error output
- one example URL if relevant