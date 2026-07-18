# news-watch

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)

<!-- BEGIN GENERATED: index-summary -->
news-watch scrapes structured news data from Indonesia's top news websites with keyword/date search and latest-news monitoring.

The current stable release supports 76 news scrapers (71 Indonesian/global sources with search mode, 76 with latest mode). 78 sources are registered in total: 1 source under investigation; 1 source quarantined.
<!-- END GENERATED: index-summary -->

## Install

```bash
pip install news-watch
newswatch --help
```

Browser-backed sources also require:

```bash
playwright install chromium
```

## Start

```bash
newswatch --keywords ihsg --start_date 2026-07-01
newswatch --method latest --scrapers "antaranews,kompas,viva"
```

```python
import newswatch as nw

df = nw.scrape_to_dataframe("ihsg", "2026-07-01")
latest = nw.latest_to_dataframe(scrapers="antaranews,kompas,viva")
```

## Documentation

- [Getting Started](getting-started.md)
- [Practical Guide](practical-guide.md)
- [Use Case MBG](use-case-mbg.md)
- [API Reference](api-reference.md)
- [Architecture](architecture.md)
- [Troubleshooting](troubleshooting.md)
- [Changelog](changelog.md)

## Source capabilities

The registry is the source of truth. List current slugs at runtime:

```bash
newswatch --method search --list_scrapers
newswatch --method latest --list_scrapers
```

Search support means the source has a verified arbitrary-keyword workflow. Latest support means it can collect current articles without a keyword. Availability can still vary by network, rate limit, and upstream changes.
