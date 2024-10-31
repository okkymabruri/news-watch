# news-watch

idnewswatch is a Python package that allows you to scrape news articles from various Indonesian news websites based on specific keywords and date ranges.


## Installation

You can install newswatch via pip:

```bash
pip install news-watch
```

## Usage

To run the scraper from the command line:

```bash
newswatch -k <your keyword> -sd <define start date>
```

### Examples

Scrape articles related to "ihsg" from October 28, 2024:

```bash
newswatch -k ihsg -sd 2024-10-28
```

Increase verbosity to see more logs:

```bash
idnewswatch -k ihsg -sd 2024-10-28 -vv
```

## Output

The scraped articles are saved as a CSV file in the current working directory with the format `news-watch-YYYYMMDD_HH.csv`.

The CSV file contains the following fields:

- `title`
- `publish_date`
- `author`
- `content`
- `keyword`
- `category`
- `source`
- `link`

## Supported Websites

- Bisnis Indonesia
- CNBC Indonesia
- Detik
- Kontan
- Viva

## Contributing

Contributions are welcome! If you'd like to add support for more websites or improve the existing code, please open an issue or submit a pull request.

### Running Tests

To run the test suite:

```bash
pytest tests/
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
