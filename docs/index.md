# news-watch: Indonesia's top news websites scraper

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)

news-watch scrapes structured news data from Indonesia's top news websites with keyword/date search and latest-news monitoring.

The current stable release supports 61 Indonesian news scrapers with search or latest mode.

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

| Source | Slug | Search | Latest | Notes |
|--------|------|--------|--------|-------|
| Antara News | `antaranews` | Yes | Yes | Strict search |
| BBC News | `bbc` | Yes | Yes | Strict search |
| Bali Post | `balipost` | No | Yes | Latest-only |
| Berita Jatim | `beritajatim` | Yes | Yes | Strict search |
| BeritaSatu | `beritasatu` | Yes | Yes | Strict search |
| Bisnis.com | `bisnis` | Yes | Yes | Browser required; Strict search |
| Bloomberg Technoz | `bloombergtechnoz` | Yes | Yes | Strict search |
| CNA Indonesia | `cnaindonesia` | No | Yes | Latest-only |
| CNBC Indonesia | `cnbcindonesia` | Yes | Yes | Strict search |
| CNN Indonesia | `cnnindonesia` | Yes | Yes | Strict search |
| DailySocial | `dailysocial` | Yes | Yes | Strict search |
| Detik | `detik` | Yes | Yes | Strict search |
| Fajar | `fajar` | Yes | Yes | Strict search |
| Galamedia | `galamedia` | Yes | Yes | Strict search |
| Gatra | `gatra` | Yes | Yes | Strict search |
| Grid | `grid` | Yes | Yes | Strict search |
| Harian Jogja | `harianjogja` | Yes | Yes | Strict search |
| Hipwee | `hipwee` | Yes | Yes | Strict search |
| IDN Times | `idntimes` | Yes | Yes | Browser required; Strict search |
| Investor.id | `investor` | Yes | Yes | Strict search |
| JPNN (Jawa Pos News Network) | `jpnn` | Yes | Yes | Strict search |
| Jakarta Globe | `jakartaglobe` | Yes | Yes | Strict search |
| Jakarta Selaras | `jakartaselarascoid` | Yes | Yes | Tag/sitemap filtered |
| Jawa Pos | `jawapos` | Yes | Yes | Strict search |
| KBR | `kbr` | Yes | Yes | Strict search |
| Kaltim Post (Borneo24) | `kaltimpost` | Yes | Yes | Strict search |
| Katadata | `katadata` | Yes | Yes | Strict search |
| Kompas | `kompas` | Yes | Yes | Strict search |
| Kontan | `kontan` | Yes | Yes | Strict search |
| Kumparan | `kumparan` | Yes | Yes | Strict search |
| Liputan6 | `liputan6` | Yes | Yes | Browser required; Strict search |
| Media Indonesia | `mediaindonesia` | Yes | Yes | Strict search |
| Merdeka | `merdeka` | Yes | Yes | Strict search |
| MetroTV News | `metrotvnews` | Yes | Yes | Strict search |
| Mojok | `mojok` | Yes | Yes | Strict search |
| Mongabay Indonesia | `mongabay` | Yes | Yes | Strict search |
| Niaga.Asia | `niagaasia` | Yes | Yes | Strict search |
| Okezone | `okezone` | Yes | Yes | Strict search |
| Pantau.com | `pantau` | Yes | Yes | Strict search |
| Pikiran Rakyat | `pikiranrakyat` | Yes | Yes | Browser required; Strict search |
| Poskota | `poskota` | Yes | Yes | Strict search |
| Project Multatuli | `projectmultatuli` | Yes | Yes | Strict search |
| RM.ID (Rakyat Merdeka) | `rmid` | Yes | Yes | Strict search |
| RMOL | `rmol` | Yes | Yes | Tag/sitemap filtered |
| RRI (RRI.co.id) | `rri` | Yes | Yes | Strict search |
| Republika | `republika` | Yes | Yes | Browser required; Strict search |
| SINDOnews | `sindonews` | Yes | Yes | Strict search |
| SWA | `swa` | Yes | Yes | Strict search |
| Suara | `suara` | Yes | Yes | Browser required; Strict search |
| Suara Merdeka | `suaramerdeka` | Yes | Yes | Strict search |
| Surabaya Pagi | `surabayapagi` | Yes | Yes | Strict search |
| TVOne | `tvone` | Yes | Yes | Strict search |
| TVRI News | `tvrinews` | Yes | Yes | Strict search |
| Tempo | `tempo` | Yes | Yes | Strict search |
| The Jakarta Post | `jakartapost` | Yes | Yes | Browser required; Strict search |
| Tirto | `tirto` | Yes | Yes | Browser required; Strict search |
| Tribunnews | `tribunnews` | Yes | Yes | Strict search |
| VOA Indonesia | `voaindonesia` | Yes | Yes | Strict search |
| VOI.id | `voi` | Yes | Yes | Strict search |
| Viva | `viva` | Yes | Yes | Strict search |
| iNews | `inews` | Yes | Yes | Strict search |

## Important Considerations

**Ethical Use**: Always respect website terms of service and implement appropriate delays between requests.

**Performance**: Works best in local environments. Cloud platforms may experience reduced performance due to anti-bot measures.

**Strict search policy**: Every listed source passes real keyword search checks.

**Latest mode rollout**: latest monitoring starts with a smaller subset of sources and expands over time.
