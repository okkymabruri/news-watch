# news-watch: Indonesia's top media websites scraper

[![PyPI version](https://badge.fury.io/py/news-watch.svg)](https://badge.fury.io/py/news-watch)
[![Build Status](https://github.com/okkymabruri/news-watch/actions/workflows/test.yml/badge.svg)](https://github.com/okkymabruri/news-watch/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/news-watch)](https://pepy.tech/projects/news-watch)


news-watch is a Python package that scrapes structured news data from [Indonesia's top media websites](#supported-websites). It features keyword and date filtering.


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

Scrape articles for multiple keywords and disable logging:

```bash
newswatch -k "ihsg,bank,keuangan" -sd 2025-01-01 --silent
```

Scrape articles for specific news website (bisnisindonesia and detik) with excel output format and disable logging:

```bash
newswatch -k "ihsg" -s "bisnisindonesia,detik" --output_format xlsx -S
```


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
- [Kompas.com](https://www.kompas.com/)
- [Katadata.co.id](https://katadata.co.id/)
- [Kontan.co.id](https://www.kontan.co.id/)
    > Note: Running this on the cloud currently leads to errors due to Cloudflare restrictions.
    >
    > Limitation: The scraper can process a maximum of 50 pages.
- [Viva.co.id](https://www.viva.co.id/)

## Contributing

Contributions are welcome! If you'd like to add support for more websites or improve the existing code, please open an issue or submit a pull request.

### Running Tests

To run the test suite:

```bash
pytest tests/
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
