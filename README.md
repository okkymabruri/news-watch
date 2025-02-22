# news-watch: Indonesia's top news websites scraper

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)


news-watch is a Python package that scrapes structured news data from [Indonesia's top news websites](#supported-websites), offering keyword and date filtering queries for targeted research

## Installation

You can install newswatch via pip:

```bash
pip install news-watch
```

## Usage

To run the scraper from the command line:

```bash
newswatch -k <keywords> -sd <start_date> -s [<scrapers>] -of <output_format> --silent
```
Command-Line Arguments

`--keywords`, `-k`: Required. A comma-separated list of keywords to scrape (e.g., -k "ojk,bank,npl").

`--start_date`, `-sd`: Required. The start date for scraping in YYYY-MM-DD format (e.g., -sd 2023-01-01).

`--scrapers`, `-s`: Optional. A comma-separated list of scrapers to use (e.g., -s "kompas,viva"). If not provided, all scrapers will be used by default.

`--output_format`, `-of`: Optional. Specify the output format (currently support csv, xlsx).

`--silent`, `-S`: Optional. Run the scraper without printing output to the console.


### Examples

Scrape articles related to "ihsg" from January 1st, 2025:

```bash
newswatch --keywords ihsg --start_date 2025-01-01
```

Scrape articles for multiple keywords (ihsg, bank, keuangan) and disable logging:

```bash
newswatch -k "ihsg,bank,keuangan" -sd 2025-01-01 --silent
```

Scrape articles for specific news website (bisnisindonesia and detik) with excel output format and disable logging:

```bash
newswatch -k "ihsg" -s "bisnisindonesia,detik" --output_format xlsx -S
```

## Run on Google Colab

You can run news-watch on Google Colab [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/okkymabruri/news-watch/blob/main/notebook/run-newswatch-on-colab.ipynb)

## Output

The scraped articles are saved as a CSV or XLSX file in the current working directory with the format `news-watch-{keywords}-YYYYMMDD_HH`.

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

- [Bisnis Indonesia](https://bisnisindonesia.id/)
- [Bloomberg Technoz](https://www.bloombergtechnoz.com/)
- [CNBC Indonesia](https://www.cnbcindonesia.com/)
- [Detik.com](https://www.detik.com/)
- [Katadata.co.id](https://katadata.co.id/)
- [Kompas.com](https://www.kompas.com/)
- [Kontan.co.id](https://www.kontan.co.id/)
- [Metrotvnews.com](https://metrotvnews.com/)
- [Tempo.co](https://www.tempo.co/)
- [Viva.co.id](https://www.viva.co.id/)


> Note: 
> - Running [Kontan.co.id](https://www.kontan.co.id/) on the cloud currently leads to errors due to Cloudflare restrictions.
> - Limitation: [Kontan.co.id](https://www.kontan.co.id/) scraper can process a maximum of 50 pages.

## Contributing

Contributions are welcome! If you'd like to add support for more websites or improve the existing code, please open an issue or submit a pull request.

### Running Tests

To run the test:

```bash
pytest tests/
```

## License

This project is licensed under the MIT - see the [LICENSE](LICENSE) file for details.

## Citing news-watch

If you use this software, please use the following BibTex entry:

```
@software{mabruri_newswatch,
  author       = {Okky Mabruri},
  title        = {{news-watch: Indonesia's top news websites scraper}},
  year         = {2025},
  url          = {https://github.com/okkymabruri/news-watch},
  license      = {MIT},
  abstract     = {news-watch is a Python package that scrapes structured news data from Indonesia's top news websites, offering keyword and date filtering queries for targeted research.},
  keywords     = {scraping, news, newswatch, newsscraper, berita, scraping-berita}
}
```

### Related Work
* [indonesia-news-scraper](https://github.com/theyudhiztira/indonesia-news-scraper)
* [news-scraper](https://github.com/binsarjr/news-scraper)