# news-watch Documentation

Welcome to news-watch, a Python package for scraping structured news data from Indonesia's leading news websites. Whether you're conducting research, building news aggregation tools, or analyzing media coverage patterns, news-watch provides both command-line and programmatic interfaces to gather Indonesian news efficiently.

## What is news-watch?

news-watch is designed specifically for the Indonesian media landscape. It understands the unique characteristics of Indonesian news sites and provides reliable data extraction from 14+ major sources including Kompas, Detik, CNN Indonesia, Bisnis.com, and many others.

Key capabilities:

- **Keyword-based search** across multiple Indonesian news sources simultaneously
- **Date range filtering** to focus on specific time periods
- **Multiple output formats** including CSV, Excel, JSON, and pandas DataFrames
- **Async-powered performance** with intelligent rate limiting
- **Platform-aware operation** that adapts to different environments

## Getting Started

1. **[Getting Started Guide](getting-started.md)** - Installation, setup, and your first scraping session
2. **[Comprehensive Guide](comprehensive-guide.md)** - Complete tutorial with examples from basic to advanced usage
3. **[API Reference](api-reference.md)** - Complete documentation of all functions and parameters
4. **[Troubleshooting](troubleshooting.md)** - Common issues and solutions

## Quick Start

```bash
pip install news-watch
playwright install chromium

# Scrape news about Indonesian banks from January 2025
newswatch --keywords "bank,kredit" --start_date 2025-01-01
```

```python
import newswatch as nw

df = nw.scrape_to_dataframe("ihsg", "2025-01-01")
print(f"Found {len(df)} stock market articles")
```

## Supported News Sources

| Source | Domain |
|--------|--------|
| Antara News | antaranews.com |
| Bisnis.com | bisnis.com |
| Bloomberg Technoz | www.bloombergtechnoz.com |
| CNBC Indonesia | www.cnbcindonesia.com |
| Detik | detik.com |
| Jawa Pos | jawapos.com |
| Katadata | katadata.co.id |
| Kompas | kompas.com |
| Kontan | kontan.co.id |
| Media Indonesia | mediaindonesia.com |
| Metro TV News | metrotvnews.com |
| Okezone | okezone.com |
| Tempo | tempo.co |
| Viva | viva.co.id |

## Important Considerations

**Ethical Use**: Always respect website terms of service and implement appropriate delays between requests.

**Performance**: Works best in local environments. Cloud platforms may experience reduced performance due to anti-bot measures.
