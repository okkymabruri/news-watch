# Getting Started with news-watch

This guide will get you up and running with news-watch in just a few minutes. We'll cover installation, basic usage, and walk through your first scraping session.

## Installation

### Basic Installation

news-watch requires Python 3.10+ and uses Playwright for browser automation. Install both:

```bash
pip install news-watch
playwright install chromium
```

### Development Environment

If you're planning to contribute or want the latest development version:

```bash
# Clone and setup
git clone https://github.com/okkymabruri/news-watch.git
cd news-watch

# Install dependencies (recommended)
uv sync --all-extras
uv run playwright install chromium

# Run commands/tests via uv
uv run newswatch --list_scrapers
uv run pytest
```

### Virtual Environment (Recommended)

For conda users (recommended setup):

```bash
conda create -n newswatch-env python=3.9
conda activate newswatch-env
pip install news-watch
playwright install chromium
```

For venv users:

```bash
python -m venv newswatch-env
source newswatch-env/bin/activate  # On Windows: newswatch-env\Scripts\activate
pip install news-watch
playwright install chromium
```

## Verify Installation

Test that everything works:

```bash
# Check available scrapers
newswatch --list_scrapers

# Should show something like:
# Available scrapers: antaranews, bisnis, bloombergtechnoz, cnbcindonesia, detik, ...
```

## Your First Scraping Session

Let's start with a simple example - scraping recent news about Indonesian banks.

### Command Line Interface

The easiest way to get started is with the command line:

```bash
# Basic usage: scrape bank-related news from January 1, 2025
newswatch --keywords "bank" --start_date "2025-01-01"

# This will create an Excel file with your results
# Look for: news-watch-bank-[timestamp].xlsx
```

Add more keywords and options:

```bash
# Multiple keywords, specific sources, with verbose output
newswatch --keywords "bank,kredit,pinjaman" --start_date "2025-01-01" \
          --scrapers "kompas,bisnis,detik" --output_format "csv" --verbose

# Save as JSON for API integration
newswatch --keywords "teknologi,startup" --start_date "2025-01-01" \
          --scrapers "detik,kompas" --output_format "json" --verbose
```

### Python API

For programmatic access and data analysis:

```python
import newswatch as nw

# Scrape articles and get a pandas DataFrame
df = nw.scrape_to_dataframe("bank", "2025-01-01")

print(f"Found {len(df)} articles")
print(f"Sources: {df['source'].unique()}")
print(f"Date range: {df['publish_date'].min()} to {df['publish_date'].max()}")
```

## Understanding the Results

Each article includes these fields:

- **title**: Article headline
- **author**: Article author (when available)
- **publish_date**: Publication date and time
- **content**: Full article text
- **keyword**: Which search keyword matched this article
- **category**: Article category (news, business, sports, etc.)
- **source**: News website name
- **link**: Original article URL

## Common Usage Patterns

### Financial News Research

Monitor Indonesian financial markets:

```python
import newswatch as nw

# Banking sector analysis
banking_news = nw.scrape_to_dataframe(
    "bank,bca,mandiri,bri,bni", 
    "2025-01-01"
)

# Compare coverage across financial news sources
financial_sources = nw.scrape_to_dataframe(
    "ekonomi,inflasi,bi rate", 
    "2025-01-01",
    scrapers="bisnis,kontan,cnbcindonesia"
)
```

### Political Coverage Analysis

Track political developments:

```python
import newswatch as nw

# Recent political news
politics = nw.quick_scrape("politik,pemerintah,dpr", days_back=1)

# Election coverage comparison
election_news = nw.scrape_to_dataframe(
    "pemilu,pilkada,kpu", 
    "2025-01-01",
    scrapers="kompas,tempo,detik"
)
```

### Technology and Startup News

Monitor Indonesian tech scene:

```python
import newswatch as nw

# Startup and fintech news
tech_news = nw.scrape_to_dataframe(
    "startup,fintech,gojek,tokopedia", 
    "2025-01-01",
    scrapers="teknologi.bisnis.com,detik"
)

# Quick daily tech roundup
daily_tech = nw.quick_scrape("teknologi,digital,ai", days_back=1)
```

## Working with the Data

Once you have your DataFrame, you can perform various analyses:

```python
import newswatch as nw
import pandas as pd

# Get the data
df = nw.scrape_to_dataframe("ekonomi", "2025-01-01")

# Basic analysis
print("Articles per source:")
print(df['source'].value_counts())

print("\nDaily article counts:")
df['date'] = pd.to_datetime(df['publish_date']).dt.date
print(df['date'].value_counts().sort_index())

# Content analysis
df['word_count'] = df['content'].str.split().str.len()
print(f"\nAverage article length: {df['word_count'].mean():.0f} words")

# Filter recent articles
recent = df[df['publish_date'] >= '2025-01-15']
print(f"\nRecent articles (>= Jan 15): {len(recent)}")
```

## Command Line Options Reference

| Option | Description | Example |
|--------|-------------|---------|
| `-k, --keywords` | Comma-separated search terms | `"bank,kredit,fintech"` |
| `-sd, --start_date` | Start date (YYYY-MM-DD) | `"2025-01-01"` |
| `-s, --scrapers` | Specific scrapers or "auto"/"all" | `"kompas,detik"` |
| `-of, --output_format` | Output format: csv, xlsx, or json | `"csv"` |
| `-o, --output_path` | Custom output file path | `"news-watch-output.csv"` |
| `-v, --verbose` | Show detailed progress | (flag only) |
| `--list_scrapers` | Show available scrapers | (flag only) |

## Next Steps

Now that you have the basics down:

1. **Explore the [API Reference](api-reference.md)** for detailed function documentation
2. **Check [Troubleshooting](troubleshooting.md)** if you encounter any issues
3. **Experiment with different keyword combinations** to find the news you need

## Performance Tips

- **Local is better**: news-watch performs best on local machines rather than cloud environments
- **Respect rate limits**: Use reasonable delays between requests (built-in)
- **Choose your scrapers**: Use specific scrapers for better performance than "all"
- **Start small**: Test with recent dates before running large historical scrapes

## Getting Help

If you run into issues:

1. Check the [Troubleshooting guide](troubleshooting.md)
2. Look at existing [GitHub Issues](https://github.com/okkymabruri/news-watch/issues)
3. Create a new issue with:
   - error message
   - your OS + Python version
   - the command you ran