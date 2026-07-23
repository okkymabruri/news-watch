# news-watch: Indonesia's top news websites scraper

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)

news-watch is a Python package that scrapes structured news data from [Indonesia's top news websites](#supported-websites), offering keyword and date filtering queries for targeted research.

> ### Ethical Considerations & Disclaimer
> **Purpose:** For educational and research purposes only. Not designed for commercial use that could be detrimental to news source providers.
>
> **User responsibility:** Comply with each website's Terms of Service and `robots.txt`. Aggressive scraping may lead to IP blocking. Scrape responsibly and respect server limitations.

## Installation

### Using pip

```bash
pip install news-watch
playwright install chromium
```

Development setup: see https://okky.dev/news-watch/getting-started/

## Performance Notes

**⚠️ Works best locally.** Cloud environments (Google Colab, servers) may experience degraded performance or blocking due to anti-bot measures.

Some scrapers may work on a local machine but fail on remote servers, Linux CI, or GitHub Actions. This usually happens because of anti-bot protection, rate limits, geolocation differences, JavaScript rendering differences, or sudden source-side changes.

### Using a proxy

When running on a server or behind anti-bot blocks, route requests through a residential/datacenter proxy. The proxy applies to every layer (aiohttp, rnet, and the Playwright fallback):

```bash
# via flag
newswatch -k ihsg -sd 2025-01-01 --proxy "http://proxy.example.com:8080"

# via env (also honors standard HTTPS_PROXY / HTTP_PROXY)
export NEWSWATCH_PROXY="socks5://proxy.example.com:1080"
newswatch -k ihsg -sd 2025-01-01
```

```python
import newswatch as nw
df = nw.scrape_to_dataframe(
    "ihsg",
    "2025-01-01",
    proxy="http://proxy.example.com:8080",
)
```

Other reliability overrides (env vars): `NEWSWATCH_USER_AGENT` (custom User-Agent), `NEWSWATCH_MAX_RETRIES` (retry count, default 3).

## Usage

To run the scraper from the command line:

```bash
newswatch --method <search|latest> -k <keywords> -sd <start_date> -s [<scrapers>] -of <output_format> -v
```

**Command-Line Arguments**

| Argument | Description |
|----------|-------------|
| `--method` | Retrieval method: `search` (default) or `latest` |
| `-k, --keywords` | Comma-separated keywords to scrape (required for `search`, optional for `latest`) |
| `-sd, --start_date` | Start date in YYYY-MM-DD format (required for `search`, ignored in `latest`) |
| `-s, --scrapers` | Scrapers to use: specific names (e.g., `"kompas,viva"`), `"auto"` (default, platform-appropriate), or `"all"` (force all, may fail) |
| `-of, --output_format` | Output format: `csv`, `xlsx`, `json`, or `jsonl` (default: csv) |
| `-o, --output_path` | Custom output file path (optional) |
| `-v, --verbose` | Show detailed logging output (default: silent) |
| `--list_scrapers` | List all supported scrapers and exit |
| `--health-report` | Run source health probes and print status table. JSON/CSV via --output_path |
| `--limit` | Maximum number of articles to collect in latest mode |
| `--max-pages` | Maximum pages to fetch per scraper in latest mode |
| `--scraper-timeout` | Per-scraper timeout in seconds |
| `--progress` | Print per-scraper progress lines |
| `--daterange` | Filter articles by an inclusive date window. Format: `YYYY-MM-DD/YYYY-MM-DD` (e.g. `2026-07-13/2026-07-14`); start = 00:00:00, end = 23:59:59.999999 of the same day |
| `--dedup-file` | Path to a previous output file (JSON/JSONL/CSV); articles with matching links are skipped |
| `--proxy` | Proxy URL for all requests (e.g. `http://proxy.example.com:8080` or `socks5://proxy.example.com:1080`). Also via `NEWSWATCH_PROXY` env |


### Examples

```bash
# Basic usage
newswatch --keywords ihsg --start_date 2025-01-01

# Latest monitoring mode
newswatch --method latest --scrapers "antaranews,kompas,viva"

# Multiple keywords with specific scraper
newswatch -k "ihsg,bank" -s "tempo" --output_format xlsx -v

# List available scrapers
newswatch --list_scrapers
```

## Python API Usage

```python
import newswatch as nw

# Basic scraping - returns list of article dictionaries
articles = nw.scrape("ekonomi,politik", "2025-01-01")
print(f"Found {len(articles)} articles")

# Get results as pandas DataFrame for analysis
df = nw.scrape_to_dataframe("teknologi,startup", "2025-01-01")
print(df['source'].value_counts())

# Latest monitoring
latest = nw.latest_to_dataframe(scrapers="antaranews,kompas,viva")
print(latest[["source", "title"]].head())

# Save directly to file
nw.scrape_to_file(
    keywords="bank,ihsg", 
    start_date="2025-01-01",
    output_path="financial_news.xlsx"
)

# Quick recent news
recent_news = nw.quick_scrape("politik", days_back=3)

# Get available news sources
sources = nw.list_scrapers()
print("Available sources:", sources)
```

See the [practical guide](docs/practical-guide.md) for end-to-end CLI and Python-API examples and common research patterns.
For interactive examples, see the [API reference notebook](notebook/api-reference.ipynb).

## Run on Google Colab

You can run news-watch on Google Colab [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/okkymabruri/news-watch/blob/main/notebook/run-newswatch-on-colab.ipynb)

## Output

The scraped articles are saved as a CSV, XLSX, JSON, or JSONL file in the current working directory with the format `news-watch-{keywords}-YYYYMMDD_HH`.

Each record has 8 fields: `title`, `publish_date`, `author`, `content`, `keyword`, `category`, `source`, `link`. (`scrape_timestamp` exists on the internal `Article` model but is not emitted to output.)

The output file contains the following columns:

- `title`
- `publish_date`
- `author`
- `content`
- `keyword`
- `category`
- `source`
- `link`

## Retrieval Methods

- `search` is the default and keeps the current keyword/date research workflow.
- `latest` is intended for latest-news monitoring and does not require keywords.

<!-- BEGIN GENERATED: readme-heading -->
## Supported Websites (79)
<!-- END GENERATED: readme-heading -->
<!-- BEGIN GENERATED: readme-sources -->
[Alinea.id](https://www.alinea.id),
[Al Jazeera](https://www.aljazeera.com),
[Antara News](https://antaranews.com),
[AP News](https://apnews.com),
[Bali Post](https://www.balipost.com),
[Banten News](https://www.bantennews.co.id),
[BBC News](https://bbc.com),
[Berita Jatim](https://beritajatim.com),
[BeritaSatu](https://www.beritasatu.com),
[Betahita](https://www.betahita.id),
[Bisnis.com](https://bisnis.com),
[Bloomberg Technoz](https://bloombergtechnoz.com),
[CNA Indonesia](https://www.cna.id),
[CNBC Indonesia](https://cnbcindonesia.com),
[CNN Indonesia](https://cnnindonesia.com),
[The Conversation Indonesia](https://theconversation.com/id),
[DailySocial](https://news.dailysocial.id),
[Dandapala](https://dandapala.com),
[DDTC News](https://news.ddtc.co.id),
[Detik](https://detik.com),
[Fajar](https://fajar.co.id),
[Galamedia](https://galamedia.pikiran-rakyat.com),
[Gatra](https://www.gatra.net),
[Good News From Indonesia](https://www.goodnewsfromindonesia.id),
[Grid](https://www.grid.id),
[Harian Jogja](https://www.harianjogja.com),
[Hipwee](https://www.hipwee.com),
[Hukumonline](https://www.hukumonline.com),
[IDN Financials](https://www.idnfinancials.com/id/),
[IDN Times](https://idntimes.com),
[IDX Channel](https://www.idxchannel.com),
[Independen.id](https://independen.id),
[Indopolitika](https://indopolitika.com),
[iNews](https://inews.id),
[Infobanknews](https://infobanknews.com),
[Investor.id](https://investor.id),
[Jakarta Globe](https://jakartaglobe.id),
[The Jakarta Post](https://thejakartapost.com),
[Jakarta Selaras](https://jakarta.selaras.co.id),
[Jawa Pos](https://jawapos.com),
[JPNN (Jawa Pos News Network)](https://jpnn.com),
[Kaltim Post (Borneo24)](https://kaltimkece.borneo24.com),
[Katadata](https://katadata.co.id),
[KBR](https://kbr.id),
[Kompas](https://kompas.com),
[Kontan](https://kontan.co.id),
[Kumparan](https://kumparan.com),
[Liputan6](https://liputan6.com),
[Media Indonesia](https://mediaindonesia.com),
[Merdeka](https://merdeka.com),
[MetroTV News](https://metrotvnews.com),
[Mojok](https://mojok.co),
[Mongabay Indonesia](https://mongabay.co.id),
[Niaga.Asia](https://www.niaga.asia),
[NTVNews.id](https://www.ntvnews.id),
[NusaBali](https://www.nusabali.com),
[Okezone](https://okezone.com),
[Pantau.com](https://www.pantau.com),
[Pikiran Rakyat](https://pikiran-rakyat.com),
[Poskota](https://poskota.co.id),
[Project Multatuli](https://projectmultatuli.org),
[Republika](https://republika.co.id),
[RM.ID (Rakyat Merdeka)](https://rm.id),
[RMOL](https://rmol.id),
[RRI (RRI.co.id)](https://rri.co.id),
[SINDOnews](https://sindonews.com),
[Suara](https://suara.com),
[Suara Merdeka](https://suaramerdeka.com),
[Surabaya Pagi](https://surabayapagi.com),
[SWA](https://swa.co.id),
[Tempo](https://tempo.co),
[Tirto](https://tirto.id),
[Tribunnews](https://tribunnews.com),
[TVOne](https://tvonenews.com),
[TVRI News](https://tvrinews.id),
[Viva](https://viva.co.id),
[VOA Indonesia](https://voaindonesia.com),
[VOI.id](https://voi.id),
[Warta Ekonomi](https://wartaekonomi.co.id)
<!-- END GENERATED: readme-sources -->

<!-- BEGIN GENERATED: readme-counts -->
> **Notes:**
> - 79 registered sources: 74 with keyword search, 79 with latest mode.
> - 77 stable scrapers in the current release: 72 with keyword search, 77 with latest mode.
> - 1 source under investigation; 1 source quarantined.
> - AP News uses topic hub pages with keyword-in-title filtering (robots disallows /search?q=*).
> - Al Jazeera is latest-only via RSS feed (search page is JS-rendered).
> - Reuters skipped (WAF blocked).
> - Use `-s all` to force-run all scrapers (may cause errors/timeouts).
> - Some sources are environment-sensitive and may fail on remote servers even if they work locally.
> - Limitation: Kontan scraper maximum 50 pages.
<!-- END GENERATED: readme-counts -->
## Contributing

Contributions are welcome. Open an issue or pull request to add a source or improve an existing one.

Keep tests with their owning behavior: shared scraper contracts in `tests/test_basescraper.py`, registry metadata and discovery in `tests/test_registry.py`, and source-specific parsing and extraction in `tests/test_scrapers_focused.py`. Do not add catch-all files such as `tests/test_new_scrapers.py`. Before adding coverage, search the owning module and extend or parameterize an existing test when it already exercises the same observable behavior. Keep another case only for a distinct boundary, precedence rule, transition, or real error path; avoid assertions on source text, private plumbing, or registry counts.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. The authors assume no liability for misuse of this software.


## Citation

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.14908389.svg)](https://doi.org/10.5281/zenodo.14908389)

```bibtex
@software{mabruri_newswatch,
  author = {Okky Mabruri},
  title = {news-watch},
  year = {2025},
  doi = {10.5281/zenodo.14908389}
}
```

### Related Work
* [indonesia-news-scraper](https://github.com/theyudhiztira/indonesia-news-scraper)
* [news-scraper](https://github.com/binsarjr/news-scraper)
