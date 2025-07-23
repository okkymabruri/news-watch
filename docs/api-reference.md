# API Reference

The news-watch Python API provides a clean, synchronous interface for integrating Indonesian news scraping into your Python projects. All functions handle the complexity of async operations internally, so you can focus on your analysis.

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
ihsg_df = nw.scrape_ihsg_news(days_back=1)                   # Stock market news
```

## Core Functions

### scrape()

The foundation function that returns raw article data.

```python
def scrape(keywords, start_date, scrapers="auto", verbose=False, timeout=300, **kwargs)
```

**Parameters:**
- `keywords` (str): What to search for. Use commas for multiple terms: `"bank,kredit,fintech"`
- `start_date` (str): When to start looking, in YYYY-MM-DD format: `"2025-01-01"`
- `scrapers` (str, optional): Which sites to scrape:
  - `"auto"` (default) - Let news-watch pick based on your platform
  - `"all"` - Try every scraper (might fail on some systems)  
  - `"kompas,detik"` - Pick specific sites by name
- `verbose` (bool, optional): Show progress details (default: False)
- `timeout` (int, optional): Max seconds to wait (default: 300)

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

Perfect for data analysis - returns a pandas DataFrame ready for immediate use.

```python
def scrape_to_dataframe(keywords, start_date, scrapers="auto", verbose=False, timeout=300, **kwargs)
```

**Parameters:**
Same as `scrape()` function.

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
```

### scrape_to_file()

Save results directly to CSV or Excel files.

```python
def scrape_to_file(keywords, start_date, output_path, output_format="xlsx", 
                  scrapers="auto", verbose=False, timeout=300, **kwargs)
```

**Parameters:**
- `keywords`, `start_date`, `scrapers`, `verbose`, `timeout`: Same as other functions
- `output_path` (str): Where to save the file
- `output_format` (str, optional): `"xlsx"`, `"csv"`, or `"json"` (default: "xlsx")

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
    scrapers="detik,kompas",
    verbose=True
)

# Save as JSON for API integration
nw.scrape_to_file(
    keywords="fintech,digital", 
    start_date="2025-01-01",
    output_path="tech_articles.json",
    output_format="json",
    scrapers="detik,kompas",
    verbose=True
)
```

## Utility Functions

### list_scrapers()

Find out which Indonesian news sites are available.

```python
def list_scrapers()
```

**Returns:**
List of scraper names you can use with the `scrapers` parameter.

**Example:**
```python
import newswatch as nw

available = nw.list_scrapers()
print("Available news sources:", available)
# Output: ['antaranews', 'bisnis', 'bloombergtechnoz', 'cnbcindonesia', 'detik', ...]

# Use specific ones for financial news
financial_sources = ["bisnis", "kontan", "cnbcindonesia"]
df = nw.scrape_to_dataframe("saham", "2025-01-01", scrapers=",".join(financial_sources))
```

### quick_scrape()

Get recent news without worrying about exact dates.

```python
def quick_scrape(keywords, days_back=1, scrapers="auto")
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
    scrapers="bisnis,detik"
)

print(f"Found {len(banking)} banking articles in last 3 days")
```

### scrape_ihsg_news()

Specialized function for Indonesian stock market news.

```python
def scrape_ihsg_news(days_back=1)
```

**Parameters:**
- `days_back` (int, optional): Days back to search (default: 1)

**Returns:**
pandas DataFrame with IHSG-related articles.

**Example:**
```python
import newswatch as nw

# Today's stock market news
today_stocks = nw.scrape_ihsg_news()

# Last week's market news
week_stocks = nw.scrape_ihsg_news(days_back=7)

# Analyze market sentiment
sentiment_words = week_stocks['title'].str.contains(
    'naik|turun|menguat|melemah|bullish|bearish', 
    case=False
)
print(f"Articles with sentiment indicators: {sentiment_words.sum()}")

# Daily market news volume
daily_counts = week_stocks.groupby(
    week_stocks['publish_date'].dt.date
).size()
print("Daily IHSG news volume:")
print(daily_counts)
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

All examples are tested, practical, and use safe generic keywords appropriate for research purposes.

## Performance Tips

- **Use specific scrapers** instead of "all" when possible
- **Start with recent dates** to test before running large historical scrapes  
- **Local environments work best** - cloud platforms may have restrictions
- **Reasonable timeouts** - increase timeout for large scraping jobs
- **Batch processing** - process results in chunks for large datasets

## Error Scenarios

Common issues and solutions:

**Empty results**: Check if your keywords are in Indonesian or try broader terms
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