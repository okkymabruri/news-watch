# news-watch: Indonesia's top news websites scraper

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)

news-watch scrapes structured news data from Indonesia's top news websites with keyword/date search and latest-news monitoring.

The current stable release supports 40 query-backed Indonesian news scrapers. No investigating or quarantined sources remain.

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
newswatch --method latest --scrapers "antaranews,kompas,viva"
```

```python
import newswatch as nw

df = nw.scrape_to_dataframe("ihsg", "2025-01-01")
print(len(df))

latest = nw.latest_to_dataframe(scrapers="antaranews,kompas,viva")
print(len(latest))
```

## Docs

- [Getting Started](getting-started.md)
- [Comprehensive Guide](comprehensive-guide.md)
- [API Reference](api-reference.md)
- [Troubleshooting](troubleshooting.md)
- [Changelog](changelog.md)

## Supported News Sources

### Stable (strict keyword search)

| Source | Domain |
|--------|--------|
| Antara News | antaranews.com |
| BBC News | bbc.com |
| BeritaJatim | beritajatim.com |
| Bisnis.com | bisnis.com |
| Bloomberg Technoz | bloombergtechnoz.com |
| CNBC Indonesia | cnbcindonesia.com |
| CNN Indonesia | cnnindonesia.com |
| Detik | detik.com |
| Galamedia | galamedia.pikiran-rakyat.com |
| IDN Times | idntimes.com |
| iNews | inews.id |
| Investor Daily | investor.id |
| Jawapos | jawapos.com |
| Jakarta Post | thejakartapost.com |
| JPNN | jpnn.com |
| Katadata | katadata.co.id |
| Kompas | kompas.com |
| Kontan | kontan.co.id |
| Kumparan | kumparan.com |
| Liputan6 | liputan6.com |
| Media Indonesia | mediaindonesia.com |
| Merdeka | merdeka.com |
| Metro TV News | metrotvnews.com |
| Mongabay Indonesia | mongabay.co.id |
| Okezone | okezone.com |
| Pikiran Rakyat | pikiran-rakyat.com |
| Poskota | poskota.co.id |
| Republika | republika.co.id |
| RM.ID | rm.id |
| RRI | rri.co.id |
| SINDOnews | sindonews.com |
| Suara | suara.com |
| Suara Merdeka | suaramerdeka.com |
| Surabaya Pagi | surabayapagi.com |
| Tempo | tempo.co |
| Tirto | tirto.id |
| Tribunnews | tribunnews.com |
| TVOne | tvonenews.com |
| TVRI News | tvrinews.id |
| Viva | viva.co.id |

## Important Considerations

**Ethical Use**: Always respect website terms of service and implement appropriate delays between requests.

**Performance**: Works best in local environments. Cloud platforms may experience reduced performance due to anti-bot measures.

**Strict search policy**: Every listed source passes real keyword search checks.

**Latest mode rollout**: latest monitoring starts with a smaller subset of sources and expands over time.
