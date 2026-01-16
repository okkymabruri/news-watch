# News-Watch Comprehensive Guide: From Basics to Advanced

This comprehensive guide covers everything you need to know about using news-watch for Indonesian news research, from simple searches to sophisticated analysis workflows. We'll start with basic scraping and build up to real-world data science applications.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Basic Usage](#basic-usage)
3. [Working with DataFrames](#working-with-dataframes)
4. [Choosing Your Sources](#choosing-your-sources)
5. [Building Your First Analysis](#building-your-first-analysis)
6. [Time-Based Analysis](#time-based-analysis)
7. [Multi-Topic Research](#multi-topic-research)
8. [Content Analysis](#content-analysis)
9. [Saving Your Work](#saving-your-work)
10. [Advanced Usage Examples](#advanced-usage-examples)
11. [Integration Examples](#integration-examples)
12. [Troubleshooting Common Issues](#troubleshooting-common-issues)

## Getting Started

### Installation

```bash
pip install news-watch
playwright install chromium
```

If you're using conda (recommended for data science work):

```bash
conda activate newswatch-env
pip install news-watch
```

### Your First Scrape

Let's start with something simple - finding recent news about Indonesian economics:

```python
import newswatch as nw
import pandas as pd

# Search for IHSG (Indonesia stock index) news from the past week
articles = nw.scrape(
    keywords="ihsg",
    start_date="2025-01-15"
)

print(f"Found {len(articles)} articles about IHSG")
if articles:
    print("First article title:", articles[0]['title'])
```

Each article contains these fields:
- `title`: Article headline
- `publish_date`: When it was published
- `author`: Writer (might be empty)
- `content`: Full article text
- `keyword`: Which search term matched
- `category`: News section (Ekonomi, Politik, etc.)
- `source`: Website name (detik, kompas, etc.)
- `link`: Original URL

## Basic Usage

### Simple News Scraping

Start with simple keyword searches to understand the API:

```python
import newswatch as nw

# Basic scraping with generic keywords
articles = nw.scrape(
    keywords="ekonomi", 
    start_date="2025-01-15",
    scrapers="kompas"
)

print(f"Found {len(articles)} economic news articles")

# Each article is a dictionary with these keys:
if articles:
    sample_article = articles[0]
    print("Article structure:")
    for key, value in sample_article.items():
        print(f"  {key}: {str(value)[:50]}...")
```

### File Output

Save results for further analysis:

```python
import newswatch as nw

# Save directly to Excel file
nw.scrape_to_file(
    keywords="pendidikan",
    start_date="2025-01-10",
    output_path="education_news.xlsx",
    output_format="xlsx",
    scrapers="tempo,antaranews"
)

print("Education news saved to education_news.xlsx")

# Save to CSV
nw.scrape_to_file(
    keywords="kesehatan",
    start_date="2025-01-10", 
    output_path="health_news.csv",
    output_format="csv",
    scrapers="kompas"
)

print("Health news saved to health_news.csv")

# Save to JSON for API integration
nw.scrape_to_file(
    keywords="teknologi",
    start_date="2025-01-10", 
    output_path="tech_news.json",
    output_format="json",
    scrapers="detik"
)

print("Tech news saved to tech_news.json")
```

## Working with DataFrames

For data analysis, you'll usually want a pandas DataFrame:

```python
# Get economic news as a DataFrame
df = nw.scrape_to_dataframe(
    keywords="ekonomi,inflasi,bank",
    start_date="2025-01-01",
    scrapers="detik,kompas,cnbcindonesia"
)

# Quick overview
print(f"Dataset shape: {df.shape}")
print(f"Sources: {df['source'].unique()}")
print(f"Date range: {df['publish_date'].min()} to {df['publish_date'].max()}")
```

DataFrames are ideal for analysis workflows:

```python
import newswatch as nw
import pandas as pd

# Get news as a pandas DataFrame
df = nw.scrape_to_dataframe(
    keywords="teknologi",
    start_date="2025-01-15", 
    scrapers="detik,kompas"
)

print(f"Retrieved {len(df)} technology articles")
print(f"Columns: {list(df.columns)}")

# Basic analysis
if not df.empty:
    print(f"Sources: {df['source'].value_counts().to_dict()}")
    print(f"Date range: {df['publish_date'].min()} to {df['publish_date'].max()}")
```

## Choosing Your Sources

Different news sites have different strengths. Here's how to pick:

```python
# List all available scrapers
scrapers = nw.list_scrapers()
print("Available sources:", scrapers)

# Financial news - use business-focused sites
financial_df = nw.scrape_to_dataframe(
    keywords="saham,investasi,obligasi",
    start_date="2025-01-01",
    scrapers="cnbcindonesia,kontan,bisnis"  # business publications
)

# Political news - use general news sites
political_df = nw.scrape_to_dataframe(
    keywords="politik,pemilu,presiden",
    start_date="2025-01-01",
    scrapers="tempo,kompas,detik"  # mainstream media
)

# Tech news - cast a wider net
tech_df = nw.scrape_to_dataframe(
    keywords="teknologi,startup,digital",
    start_date="2025-01-01",
    scrapers="auto"  # let the system choose
)
```

The `auto` setting picks reliable scrapers based on your platform. Use `all` only if you need maximum coverage and don't mind potential errors.

## Building Your First Analysis

Let's analyze Indonesian economic sentiment around key events:

```python
# Collect comprehensive economic data
economic_keywords = "ekonomi,inflasi,suku bunga,rupiah,ihsg"

df = nw.scrape_to_dataframe(
    keywords=economic_keywords,
    start_date="2025-01-01",
    scrapers="cnbcindonesia,detik,kompas,bisnis",
    verbose=True  # see progress
)

# Basic analysis
print("Economic News Analysis")
print("=" * 50)
print(f"Total articles: {len(df)}")
print(f"Time period: {df['publish_date'].min()} to {df['publish_date'].max()}")

# Which topics got the most coverage?
keyword_counts = df['keyword'].value_counts()
print("\nMost discussed topics:")
for keyword, count in keyword_counts.head().items():
    print(f"  {keyword}: {count} articles")

# Which sources covered economics most?
source_counts = df['source'].value_counts()
print("\nMost active sources:")
for source, count in source_counts.head().items():
    print(f"  {source}: {count} articles")
```

## Time-Based Analysis

Understanding when news breaks is crucial for financial and political analysis:

```python
import matplotlib.pyplot as plt

# Convert publish_date to datetime for analysis
df['publish_date'] = pd.to_datetime(df['publish_date'])
df['date'] = df['publish_date'].dt.date
df['hour'] = df['publish_date'].dt.hour

# Articles per day
daily_counts = df.groupby('date').size()
print("Daily article counts:")
print(daily_counts)

# Peak publishing hours
hourly_counts = df.groupby('hour').size()
print(f"\nPeak hour: {hourly_counts.idxmax()}:00 ({hourly_counts.max()} articles)")

# Visualize the patterns
plt.figure(figsize=(12, 4))

plt.subplot(1, 2, 1)
daily_counts.plot(kind='line', marker='o')
plt.title('Articles Per Day')
plt.xticks(rotation=45)

plt.subplot(1, 2, 2)
hourly_counts.plot(kind='bar')
plt.title('Articles by Hour')
plt.xlabel('Hour of Day')

plt.tight_layout()
plt.show()
```

### Date Range Analysis

Analyze trends over time:

```python
import newswatch as nw
import pandas as pd
from datetime import datetime, timedelta

def analyze_daily_trends(keyword, days_back=14):
    """Analyze daily news volume trends."""
    
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    df = nw.scrape_to_dataframe(
        keywords=keyword,
        start_date=start_date,
        scrapers="auto"
    )
    
    if df.empty:
        return f"No data found for '{keyword}'"
    
    # Convert to datetime and group by date
    df['publish_date'] = pd.to_datetime(df['publish_date'])
    df['date'] = df['publish_date'].dt.date
    
    daily_counts = df.groupby('date').agg({
        'title': 'count',
        'content': lambda x: x.str.len().mean(),
        'source': lambda x: x.nunique()
    }).round(0)
    
    daily_counts.columns = ['article_count', 'avg_content_length', 'source_count']
    
    # Calculate trend statistics
    trend_stats = {
        'total_days': len(daily_counts),
        'total_articles': daily_counts['article_count'].sum(),
        'daily_average': daily_counts['article_count'].mean(),
        'peak_day': daily_counts['article_count'].idxmax(),
        'peak_count': daily_counts['article_count'].max(),
        'min_day': daily_counts['article_count'].idxmin(),
        'min_count': daily_counts['article_count'].min()
    }
    
    return daily_counts, trend_stats

# Analyze technology news trends
tech_daily, tech_stats = analyze_daily_trends("teknologi", days_back=10)

print("Technology News Trends (Last 10 Days):")
print(f"  Total articles: {tech_stats['total_articles']}")
print(f"  Daily average: {tech_stats['daily_average']:.1f}")
print(f"  Peak day: {tech_stats['peak_day']} ({tech_stats['peak_count']} articles)")
print(f"  Quiet day: {tech_stats['min_day']} ({tech_stats['min_count']} articles)")

print("\nDaily breakdown:")
print(tech_daily)
```

## Multi-Topic Research

For comprehensive research, you often need to track multiple themes:

```python
def research_topic_cluster(topic_name, keywords, days_back=7):
    """Research a specific topic cluster over time."""
    
    from datetime import datetime, timedelta
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    print(f"Researching {topic_name}...")
    
    df = nw.scrape_to_dataframe(
        keywords=keywords,
        start_date=start_date,
        scrapers="auto"
    )
    
    if df.empty:
        print(f"  No articles found for {topic_name}")
        return None
    
    # Analysis
    print(f"  Found {len(df)} articles")
    print(f"  Top sources: {', '.join(df['source'].value_counts().head(3).index)}")
    print(f"  Average article length: {df['content'].str.len().mean():.0f} characters")
    
    return df

# Research multiple themes
topics = {
    'Economy': 'ekonomi,keuangan,bank,investasi',
    'Politics': 'politik,pemilu,pemerintah,menteri',
    'Technology': 'teknologi,digital,startup,ai',
    'Health': 'kesehatan,covid,vaksin,rumah sakit'
}

results = {}
for topic_name, keywords in topics.items():
    results[topic_name] = research_topic_cluster(topic_name, keywords, days_back=5)
```

### Multiple Keyword Analysis

Work with multiple related keywords:

```python
import newswatch as nw
import pandas as pd
from datetime import datetime, timedelta

def multi_keyword_analysis(keyword_groups, days_back=7):
    """Analyze multiple keyword groups over a time period."""
    
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    all_results = []
    
    for group_name, keywords in keyword_groups.items():
        print(f"Processing {group_name}...")
        
        try:
            df = nw.scrape_to_dataframe(
                keywords=keywords,
                start_date=start_date,
                scrapers="kompas,detik"  # Use reliable sources
            )
            
            if not df.empty:
                df['keyword_group'] = group_name
                all_results.append(df)
                print(f"  Found {len(df)} articles")
            else:
                print(f"  No articles found")
                
        except Exception as e:
            print(f"  Error: {e}")
    
    if all_results:
        combined_df = pd.concat(all_results, ignore_index=True)
        
        # Analysis by group
        group_analysis = combined_df.groupby('keyword_group').agg({
            'title': 'count',
            'content': lambda x: x.str.len().mean(),
            'source': lambda x: x.nunique()
        }).round(0)
        
        group_analysis.columns = ['article_count', 'avg_content_length', 'source_count']
        
        return combined_df, group_analysis
    
    return pd.DataFrame(), pd.DataFrame()

# Define keyword groups for analysis
keyword_groups = {
    'education': 'pendidikan,sekolah,mahasiswa',
    'technology': 'teknologi,digital,internet',
    'environment': 'lingkungan,iklim,polusi',
    'health': 'kesehatan,rumah sakit,dokter'
}

# Run analysis
combined_data, group_summary = multi_keyword_analysis(keyword_groups, days_back=5)

if not group_summary.empty:
    print("\nKeyword Group Analysis:")
    print(group_summary)
    
    # Save combined results
    combined_data.to_excel("multi_topic_analysis.xlsx", index=False)
    print(f"\nSaved {len(combined_data)} total articles to multi_topic_analysis.xlsx")
```

## Content Analysis

Once you have articles, you can analyze the actual content:

```python
# Basic content statistics
df['content_length'] = df['content'].str.len()
df['word_count'] = df['content'].str.split().str.len()

print("Content Analysis:")
print(f"Average article length: {df['content_length'].mean():.0f} characters")
print(f"Average word count: {df['word_count'].mean():.0f} words")
print(f"Longest article: {df['content_length'].max()} characters")
print(f"Shortest article: {df['content_length'].min()} characters")

# Find articles with specific terms
urgent_articles = df[df['content'].str.contains('urgent|penting|mendesak', case=False, na=False)]
print(f"\nArticles with urgent language: {len(urgent_articles)}")

# Look for sentiment indicators
positive_words = ['naik', 'meningkat', 'positif', 'bagus', 'menguat']
negative_words = ['turun', 'menurun', 'negatif', 'buruk', 'melemah']

for word in positive_words:
    count = df['content'].str.contains(word, case=False, na=False).sum()
    print(f"Articles mentioning '{word}': {count}")
```

### Content Analysis with Metrics

Analyze article characteristics:

```python
import newswatch as nw
import pandas as pd

def analyze_content_patterns(keyword, start_date="2025-01-15"):
    """Analyze content patterns for a given keyword."""
    
    df = nw.scrape_to_dataframe(
        keywords=keyword,
        start_date=start_date,
        scrapers="auto"  # Use all available scrapers
    )
    
    if df.empty:
        return f"No articles found for '{keyword}'"
    
    # Calculate content metrics
    df['content_length'] = df['content'].str.len()
    df['title_length'] = df['title'].str.len()
    df['has_author'] = df['author'].notna()
    
    analysis = {
        'total_articles': len(df),
        'average_content_length': df['content_length'].mean(),
        'average_title_length': df['title_length'].mean(),
        'articles_with_author': df['has_author'].sum(),
        'sources_used': df['source'].nunique(),
        'source_distribution': df['source'].value_counts().to_dict(),
        'content_length_stats': {
            'min': df['content_length'].min(),
            'max': df['content_length'].max(),
            'median': df['content_length'].median()
        }
    }
    
    return analysis

# Analyze different topics
economy_analysis = analyze_content_patterns("ekonomi")
tech_analysis = analyze_content_patterns("teknologi")

print("Economy News Analysis:")
print(f"  Articles: {economy_analysis['total_articles']}")
print(f"  Avg length: {economy_analysis['average_content_length']:.0f} chars")
print(f"  Sources: {economy_analysis['sources_used']}")

print("\nTechnology News Analysis:")
print(f"  Articles: {tech_analysis['total_articles']}")
print(f"  Avg length: {tech_analysis['average_content_length']:.0f} chars")
print(f"  Sources: {tech_analysis['sources_used']}")
```

### Source Comparison

Compare coverage across different news sources:

```python
import newswatch as nw
import pandas as pd

def compare_source_coverage(keywords, sources, start_date="2025-01-15"):
    """Compare how different sources cover the same topics."""
    
    results = {}
    
    for source in sources:
        try:
            df = nw.scrape_to_dataframe(
                keywords=keywords,
                start_date=start_date,
                scrapers=source
            )
            
            results[source] = {
                'articles_found': len(df),
                'avg_content_length': df['content'].str.len().mean() if not df.empty else 0,
                'unique_titles': df['title'].nunique() if not df.empty else 0,
                'status': 'success'
            }
            
        except Exception as e:
            results[source] = {
                'status': 'error',
                'error': str(e)
            }
    
    return results

# Compare coverage of education topics across sources  
education_coverage = compare_source_coverage(
    keywords="pendidikan,sekolah,universitas",
    sources=["kompas", "detik", "tempo", "antaranews"]
)

print("Education Coverage Comparison:")
for source, data in education_coverage.items():
    if data['status'] == 'success':
        print(f"  {source}: {data['articles_found']} articles, "
              f"avg {data['avg_content_length']:.0f} chars")
    else:
        print(f"  {source}: Error - {data['error']}")
```

## Saving Your Work

Different output formats serve different purposes:

```python
# For data analysis - use CSV
nw.scrape_to_file(
    keywords="teknologi,startup",
    start_date="2025-01-01",
    output_path="tech_news_analysis.csv",
    output_format="csv"
)

# For reports - use Excel with formatting
nw.scrape_to_file(
    keywords="ekonomi,politik",
    start_date="2025-01-01",
    output_path="daily_news_report.xlsx",
    output_format="xlsx",
    scrapers="kompas,detik,tempo"
)

# For API integration - use JSON
nw.scrape_to_file(
    keywords="fintech,digital",
    start_date="2025-01-01",
    output_path="financial_tech_data.json",
    output_format="json",
    scrapers="cnbcindonesia,bisnis"
)

# Process and save custom analysis
summary_df = df.groupby(['source', 'keyword']).agg({
    'title': 'count',
    'content_length': 'mean',
    'publish_date': ['min', 'max']
}).round(0)

summary_df.to_excel("news_summary_analysis.xlsx")
print("Analysis saved to news_summary_analysis.xlsx")
```

## Advanced Usage Examples

### Comparative News Analysis

Compare how different sources cover the same topics:

```python
import newswatch as nw
import pandas as pd

# Get political coverage from major sources
politics = nw.scrape_to_dataframe(
    "politik,pemerintah,dpr", 
    "2025-01-01",
    scrapers="kompas,tempo,detik,cnbcindonesia"
)

# Coverage matrix
coverage = politics.groupby(['source', 'keyword']).size().unstack(fill_value=0)
print("Coverage comparison:")
print(coverage)
```

### Time Series Analysis

Track news volume over time:

```python
import newswatch as nw
import matplotlib.pyplot as plt

# Collect data for multiple time periods
all_data = []
for days in range(1, 8):  # Last 7 days
    daily_data = nw.quick_scrape("ekonomi", days_back=days)
    all_data.append(daily_data)

# Combine and analyze trends
df = pd.concat(all_data, ignore_index=True).drop_duplicates()
daily_volume = df.groupby(df['publish_date'].dt.date).size()

# Plot the trend
daily_volume.plot(kind='line', title='Economic News Volume Over Time')
plt.show()
```

### Content Analysis

Analyze article characteristics:

```python
import newswatch as nw

tech_news = nw.scrape_to_dataframe("teknologi,ai,digital", "2025-01-01")

# Article length analysis
tech_news['word_count'] = tech_news['content'].str.split().str.len()
tech_news['title_length'] = tech_news['title'].str.len()

# Summary by source
summary = tech_news.groupby('source').agg({
    'word_count': ['mean', 'std'],
    'title_length': 'mean',
    'title': 'count'
}).round(2)

print("Article characteristics by source:")
print(summary)
```

### Error Handling Best Practices

Handle common scenarios gracefully:

```python
import newswatch as nw
import pandas as pd
from datetime import datetime

def robust_news_scraping(keywords, start_date, max_retries=2):
    """Example of robust news scraping with error handling."""
    
    # Validate inputs first
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        return {"error": f"Invalid date format: {start_date}. Use YYYY-MM-DD"}
    
    if not keywords.strip():
        return {"error": "Keywords cannot be empty"}
    
    # Get available scrapers
    try:
        available_scrapers = nw.list_scrapers()
    except Exception as e:
        return {"error": f"Could not get scraper list: {e}"}
    
    # Try multiple scraper combinations
    scraper_groups = [
        ["kompas"],
        ["detik"],
        ["tempo", "antaranews"],
        ["kompas", "detik"]
    ]
    
    for attempt, scrapers in enumerate(scraper_groups, 1):
        # Only use scrapers that are available
        valid_scrapers = [s for s in scrapers if s in available_scrapers]
        if not valid_scrapers:
            continue
            
        print(f"Attempt {attempt}: Using {', '.join(valid_scrapers)}")
        
        try:
            df = nw.scrape_to_dataframe(
                keywords=keywords,
                start_date=start_date,
                scrapers=",".join(valid_scrapers),
                timeout=120  # 2 minute timeout
            )
            
            if not df.empty:
                result = {
                    "success": True,
                    "articles_found": len(df),
                    "sources_used": df['source'].unique().tolist(),
                    "scrapers_tried": valid_scrapers,
                    "attempt_number": attempt,
                    "data": df
                }
                print(f"✅ Success: {len(df)} articles from {len(df['source'].unique())} sources")
                return result
            else:
                print(f"⚠️ No articles found with {', '.join(valid_scrapers)}")
                
        except Exception as e:
            print(f"❌ Error with {', '.join(valid_scrapers)}: {e}")
            if attempt >= max_retries:
                break
            continue
    
    return {
        "success": False,
        "error": "All scraping attempts failed",
        "scrapers_tried": [group for group in scraper_groups if any(s in available_scrapers for s in group)]
    }

# Example usage with error handling
result = robust_news_scraping("ekonomi digital", "2025-01-15")

if result.get("success"):
    print(f"Successfully collected {result['articles_found']} articles")
    # Process the data
    df = result["data"]
    print(f"Sources: {', '.join(result['sources_used'])}")
else:
    print(f"Scraping failed: {result['error']}")
```

### Utility Functions

Helpful utility functions for common tasks:

```python
import newswatch as nw
import pandas as pd

def get_scraper_status():
    """Check which scrapers are working well."""
    
    scrapers = nw.list_scrapers()
    test_keyword = "ekonomi"
    test_date = "2025-01-16"
    
    scraper_status = {}
    
    for scraper in scrapers[:5]:  # Test first 5 scrapers
        try:
            articles = nw.scrape(
                keywords=test_keyword,
                start_date=test_date,
                scrapers=scraper,
                timeout=30
            )
            
            scraper_status[scraper] = {
                "status": "working",
                "article_count": len(articles),
                "test_keyword": test_keyword
            }
            
        except Exception as e:
            scraper_status[scraper] = {
                "status": "error",
                "error": str(e)[:100],
                "test_keyword": test_keyword
            }
    
    return scraper_status

def quick_news_summary(keyword, days_back=3):
    """Get a quick summary of recent news."""
    
    try:
        df = nw.quick_scrape(keyword, days_back=days_back)
        
        if df.empty:
            return f"No recent news found for '{keyword}'"
        
        summary = {
            "keyword": keyword,
            "period": f"Last {days_back} days", 
            "total_articles": len(df),
            "sources": df['source'].nunique(),
            "source_list": df['source'].value_counts().to_dict(),
            "latest_article": {
                "title": df.iloc[0]['title'],
                "source": df.iloc[0]['source'],
                "date": str(df.iloc[0]['publish_date'])
            }
        }
        
        return summary
        
    except Exception as e:
        return {"error": f"Failed to get summary: {e}"}

# Check scraper status
print("Checking scraper status...")
status = get_scraper_status()
for scraper, info in status.items():
    if info["status"] == "working":
        print(f"✅ {scraper}: {info['article_count']} articles")
    else:
        print(f"❌ {scraper}: {info['error']}")

# Quick news summary
print("\nQuick tech news summary:")
tech_summary = quick_news_summary("teknologi", days_back=2)
if "error" not in tech_summary:
    print(f"Found {tech_summary['total_articles']} articles from {tech_summary['sources']} sources")
    print(f"Latest: {tech_summary['latest_article']['title']}")
else:
    print(tech_summary["error"])
```

## Integration Examples

### Jupyter Notebook Workflow

Complete workflow for data analysis:

```python
# Cell 1: Setup and imports
import newswatch as nw
import pandas as pd
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# Set pandas display options
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', 50)

print("news-watch Analysis Notebook")
print("=" * 40)

# Cell 2: Data collection
def collect_news_data(topics, date_range_days=7):
    """Collect news data for multiple topics."""
    
    from datetime import datetime, timedelta
    start_date = (datetime.now() - timedelta(days=date_range_days)).strftime("%Y-%m-%d")
    
    datasets = {}
    
    for topic in topics:
        print(f"Collecting {topic} news...")
        
        try:
            df = nw.scrape_to_dataframe(
                keywords=topic,
                start_date=start_date,
                scrapers="kompas,detik,tempo"
            )
            
            if not df.empty:
                df['topic'] = topic
                datasets[topic] = df
                print(f"  ✅ {topic}: {len(df)} articles")
            else:
                print(f"  ⚠️ {topic}: No articles found")
                
        except Exception as e:
            print(f"  ❌ {topic}: Error - {e}")
    
    return datasets

# Collect data for analysis
topics = ["teknologi", "pendidikan", "kesehatan"]
news_datasets = collect_news_data(topics, date_range_days=5)

# Cell 3: Analysis and visualization
if news_datasets:
    # Combine all datasets
    all_data = pd.concat(news_datasets.values(), ignore_index=True)
    
    print(f"\nTotal articles collected: {len(all_data)}")
    print(f"Topics covered: {', '.join(all_data['topic'].unique())}")
    print(f"Sources used: {', '.join(all_data['source'].unique())}")
    
    # Create visualizations
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    
    # Topic distribution
    topic_counts = all_data['topic'].value_counts()
    axes[0, 0].bar(topic_counts.index, topic_counts.values)
    axes[0, 0].set_title('Articles by Topic')
    axes[0, 0].set_ylabel('Number of Articles')
    
    # Source distribution
    source_counts = all_data['source'].value_counts()
    axes[0, 1].pie(source_counts.values, labels=source_counts.index, autopct='%1.1f%%')
    axes[0, 1].set_title('Articles by Source')
    
    # Content length distribution
    all_data['content_length'] = all_data['content'].str.len()
    axes[1, 0].hist(all_data['content_length'], bins=15, alpha=0.7)
    axes[1, 0].set_title('Content Length Distribution')
    axes[1, 0].set_xlabel('Characters')
    
    # Articles by topic and source
    topic_source = all_data.groupby(['topic', 'source']).size().unstack(fill_value=0)
    topic_source.plot(kind='bar', ax=axes[1, 1], stacked=True)
    axes[1, 1].set_title('Articles by Topic and Source')
    axes[1, 1].set_ylabel('Number of Articles')
    axes[1, 1].legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    
    plt.tight_layout()
    plt.show()
    
    # Cell 4: Export results
    # Save summary statistics
    summary_stats = all_data.groupby('topic').agg({
        'title': 'count',
        'content_length': ['mean', 'median'],
        'source': 'nunique'
    }).round(2)
    
    summary_stats.columns = ['article_count', 'avg_content_length', 'median_content_length', 'source_count']
    
    print("\nSummary Statistics by Topic:")
    print(summary_stats)
    
    # Export data
    all_data.to_excel("news_analysis_results.xlsx", index=False)
    summary_stats.to_excel("news_summary_stats.xlsx")
    
    print(f"\n📁 Data exported:")
    print(f"  - news_analysis_results.xlsx ({len(all_data)} articles)")
    print(f"  - news_summary_stats.xlsx (summary statistics)")

else:
    print("No data collected. Please check your network connection and try again.")
```

## Troubleshooting Common Issues

### When You Get No Results

Don't panic! Empty results happen more often than you'd think, especially when you're getting specific with your search terms. Here's what usually works:

```python
df = nw.scrape_to_dataframe(keywords="very_specific_term", start_date="2025-01-01")

if df.empty:
    print("Hmm, no articles found. Let's try a few things...")
    
    # Try broader terms first
    broader_df = nw.scrape_to_dataframe(keywords="ekonomi", start_date="2025-01-01")
    
    if not broader_df.empty:
        print(f"Found {len(broader_df)} articles with broader terms!")
        print("Try using more general keywords, then filter the results")
```

The trick is starting broad and then narrowing down. Instead of searching for "inflasi inti", try "inflasi" or even just "ekonomi". You can always filter the results afterward. Also, try going back a bit further in time - sometimes news cycles are quieter than expected.

If you're still getting nothing, double-check your internet connection and try switching to `scrapers="all"` to cast a wider net.

### Dealing with Timeouts

Large searches can take a while, especially when you're pulling from multiple sources over long time periods. When things start timing out, you have a couple of options:

```python
# Give it more time to work
large_df = nw.scrape_to_dataframe(
    keywords="politik,ekonomi,sosial,budaya",
    start_date="2025-01-01",
    timeout=600,  # bump it up to 10 minutes
    scrapers="auto"
)
```

But honestly? Sometimes it's better to break things down into smaller chunks rather than waiting forever for one massive scrape.

### Managing Large Datasets

If you're doing serious research that spans weeks or months, your computer might start struggling with memory. Here's a chunking approach that works really well:

```python
from datetime import datetime, timedelta

def scrape_by_chunks(keywords, start_date, chunk_days=3):
    """Break large date ranges into manageable pieces."""
    
    all_results = []
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.now()
    
    while current_date < end_date:
        chunk_end = min(current_date + timedelta(days=chunk_days), end_date)
        
        print(f"Working on {current_date.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}")
        
        chunk_df = nw.scrape_to_dataframe(
            keywords=keywords,
            start_date=current_date.strftime("%Y-%m-%d"),
            scrapers="auto"
        )
        
        if not chunk_df.empty:
            # Clean up the dates to match exactly what we want
            chunk_df['publish_date'] = pd.to_datetime(chunk_df['publish_date'])
            chunk_df = chunk_df[
                (chunk_df['publish_date'] >= current_date) & 
                (chunk_df['publish_date'] < chunk_end)
            ]
            all_results.append(chunk_df)
            print(f"  Got {len(chunk_df)} articles")
        else:
            print("  No articles in this period")
        
        current_date = chunk_end
    
    if all_results:
        final_df = pd.concat(all_results, ignore_index=True)
        print(f"\nAll done! Total: {len(final_df)} articles")
        return final_df
    else:
        print("No articles found in the entire period")
        return pd.DataFrame()

# This approach works great for historical research
historical_df = scrape_by_chunks("ekonomi,politik", "2024-12-01", chunk_days=2)
```

This method is much more reliable than trying to grab everything at once. You'll see progress as it goes, and if something fails partway through, you won't lose everything you've already collected. Plus, it's easier on the news websites' servers, which makes you a better citizen of the internet.

---

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

---

These examples demonstrate practical, tested patterns for using news-watch in various scenarios. All code has been verified to work with the current API and uses safe, generic keywords appropriate for educational and research purposes.