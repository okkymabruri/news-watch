# news-watch: Indonesia's top news websites scraper

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)

news-watch scrapes structured news data from Indonesia's top news websites with keyword and date filtering.

The current stable release supports 26 query-backed Indonesian news scrapers.

## Installation

```bash
pip install news-watch
```

Optional, only for local experiments with browser-backed scrapers:

```bash
playwright install chromium
```

Development setup: https://okky.dev/news-watch/getting-started/

## Quick Start

```bash
newswatch --keywords ihsg --start_date 2025-01-01
```

```python
import newswatch as nw

df = nw.scrape_to_dataframe("ihsg", "2025-01-01")
print(len(df))
```

## Docs

- [Getting Started](getting-started.md)
- [Comprehensive Guide](comprehensive-guide.md)
- [API Reference](api-reference.md)
- [Troubleshooting](troubleshooting.md)
- [Changelog](changelog.md)

## Supported News Sources

| Source | Domain |
|--------|--------|
| Antara News | antaranews.com |
| Bisnis.com | bisnis.com |
| Bloomberg Technoz | www.bloombergtechnoz.com |
| CNBC Indonesia | www.cnbcindonesia.com |
| CNN Indonesia | www.cnnindonesia.com |
| Detik | detik.com |
| IDN Times | idntimes.com |
| iNews | inews.id |
| Jawa Pos | jawapos.com |
| Katadata | katadata.co.id |
| Kompas | kompas.com |
| Kontan | kontan.co.id |
| Kumparan | kumparan.com |
| Liputan6 | www.liputan6.com |
| Media Indonesia | mediaindonesia.com |
| Merdeka | merdeka.com |
| Metro TV News | metrotvnews.com |
| Okezone | okezone.com |
| Republika | republika.co.id |
| SINDOnews | sindonews.com |
| Suara | suara.com |
| Tempo | tempo.co |
| Tirto | tirto.id |
| Tribunnews | www.tribunnews.com |
| TVOne | www.tvonenews.com |
| Viva | viva.co.id |

## Important Considerations

**Ethical Use**: Always respect website terms of service and implement appropriate delays between requests.

**Performance**: Works best in local environments. Cloud platforms may experience reduced performance due to anti-bot measures.

**Strict search policy**: Only scrapers with query-backed discovery are listed as supported. Experimental or quarantined sources are intentionally excluded.
