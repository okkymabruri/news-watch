# news-watch: Indonesia's top news websites scraper

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)


news-watch is a Python package that scrapes structured news data from [Indonesia's top news websites](#supported-websites), offering keyword and date filtering queries for targeted research


> ### ⚠️ Ethical Considerations & Disclaimer ⚠️  
> **Purpose:** For educational and research purposes only. Not designed for commercial use that could be detrimental to news source providers.
>
> **User Responsibility:** Users must comply with each website's Terms of Service and robots.txt. Aggressive scraping may lead to IP blocking. Scrape responsibly and respect server limitations.


## Installation

### Using pip (standard)
```bash
pip install news-watch
playwright install chromium
```

Development setup: see https://okky.dev/news-watch/getting-started/

## Performance Notes

**⚠️ Works best locally.** Cloud environments (Google Colab, servers) may experience degraded performance or blocking due to anti-bot measures.

Some scrapers may work on a local machine but fail on remote servers, Linux CI, or GitHub Actions. This usually happens because of anti-bot protection, rate limits, geolocation differences, JavaScript rendering differences, or sudden source-side changes.

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
| `-of, --output_format` | Output format: `csv`, `xlsx`, or `json` (default: csv) |
| `-o, --output_path` | Custom output file path (optional) |
| `-v, --verbose` | Show detailed logging output (default: silent) |
| `--list_scrapers` | List all supported scrapers and exit |


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

See the [comprehensive guide](docs/comprehensive-guide.md) for detailed usage examples and advanced patterns.
For interactive examples, see the [API reference notebook](notebook/api-reference.ipynb).

## Run on Google Colab

You can run news-watch on Google Colab [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/okkymabruri/news-watch/blob/main/notebook/run-newswatch-on-colab.ipynb)

## Output

The scraped articles are saved as a CSV, XLSX, or JSON file in the current working directory with the format `news-watch-{keywords}-YYYYMMDD_HH`.

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
- Latest mode currently starts with a smaller subset of sources than the full search catalog.

## Supported Websites (43)

[Antara News](https://antaranews.com),
[BBC News](https://bbc.com),
[Berita Jatim](https://beritajatim.com),
[Bisnis.com](https://bisnis.com),
[Bloomberg Technoz](https://bloombergtechnoz.com),
[CNBC Indonesia](https://cnbcindonesia.com),
[CNN Indonesia](https://cnnindonesia.com),
[Detik](https://detik.com),
[Galamedia](https://galamedia.pikiran-rakyat.com),
[IDN Times](https://idntimes.com),
[iNews](https://inews.id),
[Investor Daily](https://investor.id),
[Jawapos](https://jawapos.com),
[Jakarta Post](https://thejakartapost.com),
[JPNN](https://jpnn.com),
[Katadata](https://katadata.co.id),
[Kompas](https://kompas.com),
[Kontan](https://kontan.co.id),
[Kumparan](https://kumparan.com),
[Liputan6](https://liputan6.com),
[Media Indonesia](https://mediaindonesia.com),
[Merdeka](https://merdeka.com),
[Metro TV News](https://metrotvnews.com),
[Mongabay Indonesia](https://mongabay.co.id),
[Okezone](https://okezone.com),
[Pantau.com](https://www.pantau.com),
[Pikiran Rakyat](https://pikiran-rakyat.com),
[Poskota](https://poskota.co.id),
[Republika](https://republika.co.id),
[RM.ID](https://rm.id),
[RRI](https://rri.co.id),
[SINDOnews](https://sindonews.com),
[Suara](https://suara.com),
[Suara Merdeka](https://suaramerdeka.com),
[Surabaya Pagi](https://surabayapagi.com),
[Tempo](https://tempo.co),
[Tirto](https://tirto.id),
[Tribunnews](https://tribunnews.com),
[TVOne](https://tvonenews.com),
[TVRI News](https://tvrinews.id),
[VOA Indonesia](https://voaindonesia.com),
[VOI.id](https://voi.id),
[Viva](https://viva.co.id)

> **Notes:**
> - Use `-s all` to force-run all scrapers (may cause errors/timeouts).
> - Some sources are environment-sensitive and may fail on remote servers even if they work locally.
> - Limitation: Kontan scraper maximum 50 pages.

## Contributing

Contributions are welcome! If you'd like to add support for more websites or improve the existing code, please open an issue or submit a pull request.

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
