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

```bash
pip install news-watch
playwright install chromium

# Development version
pip install git+https://github.com/okkymabruri/news-watch.git@dev
```

## Performance Notes

**⚠️ Works best locally.** Cloud environments (Google Colab, servers) may experience degraded performance or blocking due to anti-bot measures.

## Usage

To run the scraper from the command line:

```bash
newswatch -k <keywords> -sd <start_date> -s [<scrapers>] -of <output_format> -v
```

**Command-Line Arguments**

| Argument | Description |
|----------|-------------|
| `-k, --keywords` | **Required.** Comma-separated keywords to scrape (e.g., `"ojk,bank,npl"`) |
| `-sd, --start_date` | **Required.** Start date in YYYY-MM-DD format (e.g., `2025-01-01`) |
| `-s, --scrapers` | Scrapers to use: specific names (e.g., `"kompas,viva"`), `"auto"` (default, platform-appropriate), or `"all"` (force all, may fail) |
| `-of, --output_format` | Output format: `csv`, `xlsx`, or `json` (default: csv) |
| `-v, --verbose` | Show detailed logging output (default: silent) |
| `--list_scrapers` | List all supported scrapers and exit |


### Examples

```bash
# Basic usage
newswatch --keywords ihsg --start_date 2025-01-01

# Multiple keywords with specific scraper
newswatch -k "ihsg,bank" -s "detik" --output_format xlsx -v

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

## Supported Websites

- [Antaranews.com](https://www.antaranews.com/)
- [Bisnis.com](https://www.bisnis.com/)
- [Bloomberg Technoz](https://www.bloombergtechnoz.com/)
- [CNBC Indonesia](https://www.cnbcindonesia.com/)
- [Detik.com](https://www.detik.com/)
- [Jawapos.com](https://www.jawapos.com/)
- [Katadata.co.id](https://katadata.co.id/)
- [Kompas.com](https://www.kompas.com/)
- [Kontan.co.id](https://www.kontan.co.id/)
- [Media Indonesia](https://mediaindonesia.com/)
- [Metrotvnews.com](https://metrotvnews.com/)
- [Okezone.com](https://www.okezone.com/)
- [Tempo.co](https://www.tempo.co/)
- [Viva.co.id](https://www.viva.co.id/)


> **Note:** 
> - On Linux platforms: [Kontan](https://www.kontan.co.id/), [Jawapos](https://www.jawapos.com/), [Katadata](https://katadata.co.id/) are automatically excluded due to compatibility issues. Use `-s all` to force (may cause errors)
> - Limitation: Kontan scraper maximum 50 pages

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
