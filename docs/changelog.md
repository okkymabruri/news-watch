# Changelog

All notable changes to news-watch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-01-16

### Added
- New scrapers: CNN Indonesia, Liputan6, Tribunnews
- MkDocs documentation site and GitHub Pages deploy workflow
- Tag-based release automation (GitHub Release + PyPI publish) and Makefile release targets
- Version bump script (`scripts/version.py`) that also syncs `CITATION.cff`

### Changed
- Packaging migrated to `pyproject.toml` + `uv` (lockfile-based installs)
- Package moved to `src/` layout
- Minimal network scraper test keyword switched to `ihsg` for stability

### Fixed
- Linux CI scraping reliability via Playwright fallback when sources are blocked or return challenge pages
- RSS fallbacks for blocked search/API endpoints across multiple scrapers

### Documentation
- Updated docs and README for new scrapers, new layout, docs site, and release workflow

## [0.3.0] - 2025-07-22

### Added
- Python API with 6 core functions and structured exception hierarchy
- Data models (Article, ScrapeResult classes) for better data handling

### Changed  
- Fixed incorrect news source domains and removed speculative content
- Replaced impractical shell examples with proper Python code blocks
- Consolidated documentation into comprehensive guide
- Updated main README to showcase Python API alongside CLI

### Fixed
- Async queue coordination race conditions and timeout issues

## [0.2.5] - 2025-01-15

### Added
- **Antaranews scraper** support
- **Error handling** with custom exceptions
- **Timeout handling** improvements
- **Date parsing** improvements

### Changed
- **Metrotvnews scraper** improvements
- **Concurrency optimization** for better stability
- **Producer-consumer architecture** for better memory management
- **Input validation** improvements

### Fixed
- **Okezone scraper** reliability issues
- **Date extraction** robustness
- **Linux platform** stability

### Documentation
- **Enhanced README** with guides

## [0.2.4] - 2024-12-15

### Added
- **Multi-platform support** with automatic scraper selection based on OS
- **Verbose logging mode** for debugging and monitoring
- **Excel output format** in addition to CSV
- **Multiple keyword filtering** with comma-separated support

### Changed
- **Async architecture** using aiohttp
- **Error recovery** with exponential backoff
- **Memory efficiency** through streaming output

### Fixed
- **Date filtering accuracy**
- **Content extraction** across different sites

## [0.2.3] - 2024-11-20

### Added
- **Playwright integration** for JavaScript-heavy sites
- **Content quality filtering** with minimum length requirements
- **Source diversity** supporting 14+ Indonesian news websites

### Changed
- **CLI interface** with intuitive command-line arguments
- **Output formatting** standardized across all scrapers

### Fixed
- **Rate limiting** for website rate limits
- **Character encoding** for Indonesian text

## [0.2.2] - 2024-10-15

### Added
- **Detik.com scraper**
- **Kompas.com scraper**
- **Tempo.co scraper**
- **Date range filtering**

### Changed
- **Base scraper architecture** with unified interface
- **Error handling** per scraper

## [0.2.1] - 2024-09-10

### Added
- **CNBC Indonesia scraper**
- **Kontan scraper**
- **Bisnis.com scraper**

### Fixed
- **URL parsing** for relative and absolute URLs
- **Content extraction** algorithms

## [0.2.0] - 2024-08-05

### Added
- **Async scraping engine**
- **Multiple news sources** for Indonesian websites
- **CLI interface**
- **CSV output**

### Changed
- **Breaking change**: New CLI syntax and Python API
- **Performance**: 10x faster with async/await
- **Architecture**: Modular scraper design

## [0.1.5] - 2024-07-01

### Added
- **Scraping functionality** for select Indonesian news sites
- **Keyword search** with article filtering
- **JSON output**

### Fixed
- **HTTP handling** for network requests
- **Text encoding** for Indonesian characters

## [0.1.0] - 2024-06-01

### Added
- **Initial release** with news scraping prototype
- **Single source support**
- **Article extraction functionality**

---

## Migration Guide

### From v0.2.4 to v0.2.5

Python API migration:

**Old CLI-only approach:**
```bash
newswatch --keywords "ekonomi,politik" --start_date 2025-01-01 --output_format xlsx
```

**New API approach:**
```python
import newswatch as nw
df = nw.scrape_to_dataframe(keywords="ekonomi,politik", start_date="2025-01-01")
```

### From v0.1.x to v0.2.x

Breaking changes in v0.2.0:

- **CLI syntax changed** - Use `newswatch` instead of previous commands
- **Output format** - New standardized article structure
- **Dependencies** - Requires Python 3.10+ and async libraries

## Support

For bug reports and feature requests, please visit our [GitHub Issues](https://github.com/okkymabruri/news-watch/issues).

For general questions and discussion, see our [documentation](https://github.com/okkymabruri/news-watch/tree/main/docs).