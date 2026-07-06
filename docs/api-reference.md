# API Reference

## Quick Reference

```python
import newswatch as nw

# Core scraping functions
articles = nw.scrape("bank", "2025-01-01")                    # Returns list of dicts
df = nw.scrape_to_dataframe("bank", "2025-01-01")            # Returns pandas DataFrame  
nw.scrape_to_file("bank", "2025-01-01", "output.xlsx")       # Saves to file

# Convenience functions
scrapers = nw.list_scrapers()                                # Get available scrapers
recent_df = nw.quick_scrape("politik", days_back=3)          # Recent articles
latest_df = nw.latest_to_dataframe(scrapers="antaranews,kompas")
```

## Stable API (1.0)

From 1.0 onward, the following public surface follows [Semantic Versioning](https://semver.org/) — no breaking changes within a major version:

- **Scraping:** `scrape`, `scrape_to_dataframe`, `scrape_to_file`, `quick_scrape`
- **Latest monitoring:** `latest`, `latest_to_dataframe`, `latest_to_file`
- **Health:** `health_report`, `health_report_to_dataframe`, `health_report_to_file`
- **Registry / discovery:** `list_scrapers`, `SCRAPERS`, `get_scraper_by_slug`, `get_stable_slugs`, `get_stable_scrapers`

**Output schema (8 fields):** `title`, `publish_date`, `author`, `content`, `keyword`, `category`, `source`, `link`. The internal `Article` model also carries `scrape_timestamp`, which is intentionally not emitted to output.

## Core Functions

### scrape()

The foundation function that returns raw article data.

```python
def scrape(keywords=None, start_date=None, scrapers="auto", verbose=False, timeout=300, method="search", *, proxy=None, **kwargs):
    ...
```

**Parameters:**

- `keywords` (str, optional): What to search for. Required in `method="search"`, optional in `method="latest"`
- `start_date` (str, optional): When to start looking, in YYYY-MM-DD format. Required in `method="search"`, ignored in `method="latest"`
- `scrapers` (str, optional): Which sites to scrape:
  - `"auto"` (default) - Let news-watch pick based on your platform
  - `"all"` - Try every scraper (might fail on some systems)
  - `"kompas,tempo"` - Pick specific sites by name
- `verbose` (bool, optional): Show progress details (default: False)
- `timeout` (int, optional): Max seconds to wait (default: 300)
- `method` (str, optional): `"search"` (default) for keyword/date research, or `"latest"` for latest-news monitoring
- `proxy` (str, optional): Proxy URL applied to all requests (aiohttp, rnet, Playwright). E.g. `"http://proxy.example.com:8080"` or `"socks5://proxy.example.com:1080"`. Sets `NEWSWATCH_PROXY`. Available on all scraping/latest functions.

**Returns:**

List of dictionaries, each containing:

- `title` - Article headline
- `author` - Writer name (when available)
- `publish_date` - When it was published
- `content` - Full article text
- `keyword` - Which search term matched
- `category` - Article section (news, business, etc.)
- `source` - Website name
- `link` - Original URL

**Example:**
```python
import newswatch as nw

# Basic search
articles = nw.scrape("bank", "2025-01-01")
print(f"Found {len(articles)} articles")

# Latest monitoring
latest_articles = nw.scrape(method="latest", scrapers="antaranews,kompas")
print(f"Found {len(latest_articles)} latest articles")

# More specific search
financial_articles = nw.scrape(
    keywords="ihsg,saham,obligasi",
    start_date="2025-01-15", 
    scrapers="bisnis,kontan",
    verbose=True
)

# Process the raw data
for article in financial_articles:
    print(f"{article['title']} - {article['source']}")
    if "ihsg" in article['title'].lower():
        print("  -> Stock market related!")
```

### scrape_to_dataframe()

Returns a pandas DataFrame ready for analysis.

```python
def scrape_to_dataframe(
    keywords=None, start_date=None, scrapers="auto",
    verbose=False, timeout=300, method="search",
    limit=None, max_pages=None, *,
    scraper_timeout=None, time_range=None, dedup_file=None,
    proxy=None, **kwargs,
):
    ...
```

**Parameters:**
Same as `scrape()` function, plus:
- `method` (str, optional): `"search"` (default) or `"latest"`.
- `limit` (int | None): Maximum articles to collect (latest mode).
- `max_pages` (int | None): Maximum pages per scraper (latest mode).
- `scraper_timeout` (int | None): Per-scraper timeout in seconds.
- `time_range` (str | None): Filter by ISO8601/ISO8601 window.
- `dedup_file` (str | None): Previous output file to skip duplicates.
- `proxy` (str | None): Proxy URL for all requests. Sets `NEWSWATCH_PROXY` for the duration of the call.

**Returns:**
pandas DataFrame with the same columns as `scrape()`, but with `publish_date` automatically converted to datetime for easy filtering and analysis.

**Example:**
```python
import newswatch as nw
import pandas as pd

# Get DataFrame for analysis
df = nw.scrape_to_dataframe("teknologi", "2025-01-01")

# Immediate pandas operations
print(f"Articles per source:")
print(df['source'].value_counts())

print(f"Date range: {df['publish_date'].min()} to {df['publish_date'].max()}")

# Filter and analyze
recent = df[df['publish_date'] >= '2025-01-15']
print(f"Recent articles: {len(recent)}")

# Word count analysis
df['word_count'] = df['content'].str.split().str.len()
avg_length = df.groupby('source')['word_count'].mean()
print("Average article length by source:")
print(avg_length.sort_values(ascending=False))

# Latest articles as a DataFrame
latest_df = nw.scrape_to_dataframe(method="latest", scrapers="antaranews,kompas")
print(latest_df[["source", "title"]].head())
```

### scrape_to_file()

Save results directly to CSV or Excel files.

```python
def scrape_to_file(
    keywords, start_date, output_path, output_format="xlsx",
    scrapers="auto", verbose=False, timeout=300, method="search",
    limit=None, max_pages=None, *,
    scraper_timeout=None, time_range=None, dedup_file=None,
    proxy=None, **kwargs,
):
    ...
```

**Parameters:**
- `keywords`, `start_date`, `scrapers`, `verbose`, `timeout`: Same as other functions
- `output_path` (str): Where to save the file
- `output_format` (str, optional): `"xlsx"`, `"csv"`, `"json"`, or `"jsonl"` (default: "xlsx")
- `method` (str, optional): `"search"` (default) or `"latest"`.
- `limit` (int | None): Maximum articles to collect (latest mode).
- `max_pages` (int | None): Maximum pages per scraper (latest mode).
- `scraper_timeout` (int | None): Per-scraper timeout in seconds.
- `time_range` (str | None): Filter by ISO8601/ISO8601 window.
- `dedup_file` (str | None): Previous output file to skip duplicates.
- `proxy` (str | None): Proxy URL for all requests. Sets `NEWSWATCH_PROXY` for the duration of the call.

**Returns:**
Nothing - file is saved to the specified location.

**Example:**
```python
import newswatch as nw

# Save as Excel (default)
nw.scrape_to_file(
    keywords="ekonomi,inflasi", 
    start_date="2025-01-01",
    output_path="economic_news.xlsx"
)

# Save as CSV with specific sources
nw.scrape_to_file(
    keywords="startup,unicorn,fintech", 
    start_date="2025-01-01",
    output_path="/path/to/startup_news.csv",
    output_format="csv",
    scrapers="tempo,kompas",
    verbose=True
)

# Save as JSON for API integration
nw.scrape_to_file(
    keywords="fintech,digital", 
    start_date="2025-01-01",
    output_path="tech_articles.json",
    output_format="json",
    scrapers="tempo,kompas",
    verbose=True
)

# Save latest articles directly
nw.latest_to_file(
    output_path="latest_articles.json",
    output_format="json",
    scrapers="antaranews,kompas"
)
```

## Utility Functions

### list_scrapers()

Find out which Indonesian news sites are available.

```python
def list_scrapers(method="search"):
    ...
```

**Returns:**
List of scraper names you can use with the `scrapers` parameter for the selected method.

**Example:**
```python
import newswatch as nw

available = nw.list_scrapers()
print("Available news sources:", available)
# Output: ['antaranews', 'bbc', 'bisnis', 'bloombergtechnoz', 'cnbcindonesia', ...]

# Use specific ones for financial news
financial_sources = ["bisnis", "kontan", "cnbcindonesia"]
df = nw.scrape_to_dataframe("saham", "2025-01-01", scrapers=",".join(financial_sources))
```

### latest()

Fetch newest articles without requiring keywords.

```python
def latest(scrapers="auto", verbose=False, timeout=300):
    ...
```

### latest_to_dataframe()

Fetch newest articles and return them as a pandas DataFrame.

```python
def latest_to_dataframe(scrapers="auto", verbose=False, timeout=300):
    ...
```

### quick_scrape()

Get recent news without worrying about exact dates.

```python
def quick_scrape(keywords, days_back=1, scrapers="auto"):
    ...
```

**Parameters:**
- `keywords` (str): What to search for
- `days_back` (int, optional): How many days back to look (default: 1)
- `scrapers` (str, optional): Which sources to use (default: "auto")

**Returns:**
pandas DataFrame with recent articles.

**Example:**
```python
import newswatch as nw

# Yesterday's political news
politics = nw.quick_scrape("politik")

# Tech news from the last week
tech_week = nw.quick_scrape("teknologi,startup", days_back=7)

# Banking news from last 3 days, specific sources
banking = nw.quick_scrape(
    "bank,kredit", 
    days_back=3, 
    scrapers="bisnis,tempo"
)

print(f"Found {len(banking)} banking articles in last 3 days")
```



## Working with Multiple Keywords

You can search for multiple topics at once:

```python
import newswatch as nw

# Multiple related terms
banking = nw.scrape_to_dataframe("bank,bca,mandiri,bri,bni", "2025-01-01")

# See which keyword matched each article
keyword_counts = banking['keyword'].value_counts()
print("Articles found per keyword:")
print(keyword_counts)

# Filter by specific keyword
bca_articles = banking[banking['keyword'] == 'bca']
print(f"BCA-specific articles: {len(bca_articles)}")
```

## Error Handling

The API includes structured error handling:

```python
import newswatch as nw
from newswatch.exceptions import ValidationError, NewsWatchError

try:
    df = nw.scrape_to_dataframe("invalid-keyword", "not-a-date")
except ValidationError as e:
    print(f"Input validation failed: {e}")
except NewsWatchError as e:
    print(f"Scraping error occurred: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Advanced Usage Examples

For comprehensive examples including comparative analysis, time series analysis, content analysis, error handling best practices, integration patterns, and troubleshooting guides, see our **[Comprehensive Guide](comprehensive-guide.md)**.

The comprehensive guide covers:

- **Multi-topic research workflows**
- **Content analysis and sentiment detection**
- **Source comparison and coverage analysis**
- **Time-based analysis and trend detection**
- **Error handling best practices**
- **Integration with Jupyter notebooks**
- **Large dataset management strategies**
- **Troubleshooting common issues**

<!-- BEGIN GENERATED: api-notes -->
## Stable API Notes

All 63 registered scrapers are exposed via `list_scrapers()` and the public `SCRAPERS` mapping. 60 of them support the `search` method; all 63 support `latest`.
<!-- END GENERATED: api-notes -->
```python
# Too specific
df = nw.scrape_to_dataframe("very-specific-term", "2025-01-01")  # Might be empty

# Better approach
df = nw.scrape_to_dataframe("ekonomi,bisnis", "2025-01-01")  # More likely to find articles
```

**Timeout errors**: Increase timeout for large jobs
```python
# For large scraping jobs
df = nw.scrape_to_dataframe("politik", "2024-01-01", timeout=600)  # 10 minutes
```

**Platform issues**: Some scrapers work better on different operating systems
```python
# Let news-watch choose appropriate scrapers
df = nw.scrape_to_dataframe("berita", "2025-01-01", scrapers="auto")
```
