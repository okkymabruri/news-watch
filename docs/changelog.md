# Changelog

All notable changes to news-watch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.2] - 2026-07-19

### Added
- Indopolitika (`indopolitika`) with bounded native HTML search and latest-index discovery
- Infobanknews (`infobanknews`) with WordPress REST search/latest discovery and IDX Channel (`idxchannel`) with bounded sitemap-based search/latest discovery

### Changed
- Promoted Dandapala to stable latest-only support after a successful live probe, quarantined Investor.id after repeated CloudFront 403 responses, and corrected Banten News to HTTP-only investigating metadata
- Consolidated temporary new-source scraper contracts into their permanent focused, registry, and shared test modules

### Fixed
- Enforced every-token relevance filtering for GNFI and Indopolitika keyword search while leaving latest-mode discovery unfiltered

## [1.2.1] - 2026-07-18

### Changed
- Declared Python 3.10–3.12 support explicitly because the pinned browser dependency chain is not compatible with Python 3.13

### Fixed
- Restored the package introduction, ethical-use notice, installation instructions, and valid Python examples in the README and PyPI long description
- Published the MBG person co-mention network on an opaque white canvas and improved the UMAP figure's width fit
- Added release validation for temporary README markers, Markdown fences, Python examples, installation commands, and PNG transparency


## [1.2.0] - 2026-07-18

### Added
- DDTC News (`ddtcnews`), IDN Financials (`idnfinancials`), and Warta Ekonomi (`wartaekonomi`) with search and latest support
- Banten News (`bantennews`) as investigating with search and latest support, and Dandapala (`dandapala`) as investigating with latest support
- Aggregate-only MBG research guide covering collection, topic modeling, sentiment, named entities, person co-mentions, and cleaned-news document similarity

### Changed
- `--daterange` is the canonical CLI date filter, and Python `time_range=` accepts the same inclusive, date-only `YYYY-MM-DD/YYYY-MM-DD` value; internal names `args.time_range` and `_parse_time_range` remain unchanged
- Registry status for Investor changed to `investigating` because current HTTP and browser paths return persistent CloudFront 403 responses
- Scraper contracts are consolidated by behavior and capability instead of temporary catch-all test modules

### Fixed
- Kumparan latest collection uses its active RSS feed
- SurabayaPagi search is bounded and latest collection uses its RSS feed
- Suara, RMOL, Banten News, Dandapala, DDTC News, IDN Financials, and Warta Ekonomi parsing and retrieval behavior is aligned with current publisher pages

### Removed
- Removed `--time-range` CLI compatibility alias; use `--daterange`

## [1.1.0] - 2026-07-13
### Added
- Alinea.id, Betahita, Good News From Indonesia, NusaBali, and The Conversation Indonesia with search and latest support
- Hukumonline and Independen.id with latest support
- Independen.id replaces BenarNews, whose Indonesian edition stopped publishing on 3 April 2025
- Deterministic capability contracts for generic and custom search/latest workflows
- Total stable scrapers: 70 (66 search-capable, all 70 latest-capable)

### Changed
- CNA Indonesia now supports server-rendered topic search
- SINDOnews latest discovery now parses its RSS feed
- Live scraper tests skip only known external failures; unexpected parser defects fail

### Fixed
- Registry notes no longer carry stale promotion labels or historical dates
- Bali Post remains latest-only because its search endpoint is a JavaScript-only Google CSE shell

## [1.0.1] - 2026-07-12

### Added
- Append-only JSONL health history persistence (`--health-history` flag, `NEWSWATCH_HEALTH_HISTORY` env, flag-overrides-env precedence) wired into `--health-report`
- Registry-driven source documentation: doc generator emits source blocks from the registry; Makefile `sources` targets and six marked doc regions now reflect registry output
- Required/offline test split: lint, sources-check, and unit tests run deterministically; live scraper checks moved to an advisory, sharded, cached matrix

### Fixed
- JPNN: parse English month dates as DMY in article metadata
- BeritaSatu: match the current article body selector
- Republika: trust tag-page search relevance so tag results surface in strict search
- Offline test isolation: skip `browser_required` slugs in the required offline suite (search and latest)
- Docs: restore registry-driven source documentation after prior drift

### Changed
- Live scraper probes: cache results and skip on upstream flakes to reduce CI noise

## [1.0.0] - 2026-06-06

### Added
- Proxy support across all request layers (aiohttp, rnet, Playwright): `--proxy` CLI flag, `proxy=` parameter on all scraping/latest API functions, and `NEWSWATCH_PROXY` env var (honors standard `HTTPS_PROXY`/`HTTP_PROXY`)
- `NEWSWATCH_USER_AGENT` and `NEWSWATCH_MAX_RETRIES` env overrides
- New `newswatch.config` module centralizing runtime env config (proxy, user-agent, retries)
- Stable API (1.0) declaration in API reference — SemVer guarantee on the documented public surface
- First stable release; public API frozen under SemVer

### Changed
- Expanded anti-bot block detection (`_looks_blocked`) with markers: "just a moment", DataDome, PerimeterX, px-captcha, DDoS-Guard, "please enable javascript", Akamai "reference #"

### Fixed
- Docs: README CLI table now lists `jsonl` output, `--time-range`, `--dedup-file`, `--proxy`
- Docs: documented the canonical 8-field output schema (clarified `scrape_timestamp` is internal-only)

## [0.9.0] - 2026-05-29

### Added
- Health report mode via `--health-report` flag
- Health report API: `health_report()`, `health_report_to_dataframe()`, `health_report_to_file()`
- JSONL export support for health report
- AP News scraper (search via topic hub, latest via homepage)
- Al Jazeera scraper (latest via RSS feed)
- Registry metadata flags: `supports_search`, `supports_latest`, `browser_required`, `strict_search`
- Tests for health report module and CLI health mode
- Total stable scrapers: 63

### Fixed
- Health report: preserve `timeout` / `error` statuses when no articles collected
- Health report: CSV export with mixed supported/unsupported rows uses union of all fieldnames
- Health report: `--scraper-timeout 0` no longer silently overridden to `30`
- AP News: keyword URL encoding for special characters
- AP News: URL error message includes `jsonl`
- Katadata: latest mode rewritten after site removed search
- Tirto: latest mode override to avoid empty base method results
- Marked Beritasatu as `browser_required`

## [0.8.9] - 2026-05-23

### Added
- Added Fajar (`fajar`) scraper with search and latest support
- Added Mojok (`mojok`) scraper with search and latest support
- Added Grid (`grid`) scraper with search and latest support
- Added Hipwee (`hipwee`) scraper with search and latest support
- Added Jakarta Globe (`jakartaglobe`) scraper with search and latest support
- Added RMOL (`rmol`) scraper with tag-based search and latest support
- Added CNA Indonesia (`cnaindonesia`) scraper (latest-only; search uses Algolia JS)
- Added Niaga.Asia (`niagaasia`) scraper with search and latest support
- Added Jakarta Selaras (`jakartaselarascoid`) scraper with search and latest support
- Total stable scrapers: 61
- Docs: replaced 2-column table with Source|Slug|Search|Latest|Notes support matrix

### Fixed
- Mojok link filtering: added /cdn-cgi/, /login/, /wp- skips; tightened regex
- Hipwee link filtering: added /cdn-cgi/, /dashboard/, /profile/, /login/ skips
- Fajar category extraction: use meta article:section not URL year
- RMOL latest pagination: returns None after page 1 to avoid repeated pages
- RMOL registry name: changed to "RMOL" (was "RM.ID" conflicting with rmid)
- Jakarta Selaras: fixed AttributeError on undefined current_keyword
- VOI latest: fixed parse_latest_article_links excluding all article URLs
- Viva: added null guards for unguarded .find().get_text() calls
- Suara Merdeka: fixed build_latest_url page>1 using search endpoint with no query
- TVRI News: fixed category extraction for subdomain URLs
- RM.ID: fixed keyword filter using only first keyword for multi-keyword searches
- Suara: fixed cross-page deduplication (seen_urls reset inside loop)

## [0.8.5] - 2026-05-16

### Added
- Added VOA Indonesia (`voaindonesia`) scraper with search and latest support
- Added Gatra (`gatra`) scraper with search and latest support
- Added Project Multatuli (`projectmultatuli`) scraper with search and latest support
- Added DailySocial (`dailysocial`) scraper with search and latest support
- Added Kaltim Post (`kaltimpost`) scraper with search and latest support
- Added Bali Post (`balipost`) scraper (latest-only)
- Added Harian Jogja (`harianjogja`) scraper with search and latest support
- Added SWA (`swa`) scraper with search and latest support
- Added BeritaSatu (`beritasatu`) scraper with search and latest support
- Added KBR (`kbr`) scraper with search and latest support
- Total stable scrapers: 52

### Changed
- Replaced raw dict literal registry with tuple-based `_SCRAPER_ENTRIES` + `build_registry()` builder
- Added registry validation guardrails (duplicate slug/module/class_name detection, missing-file checks)
- Added `tests/test_registry.py` with 8 integrity tests

### Notes
- VOA Indonesia uses `/s?k=` endpoint with HTML parsing
- Gatra uses `/?s=` WordPress search with active-keyword title filtering
- Project Multatuli uses Elementor search endpoint
- DailySocial uses WordPress search on news.dailysocial.id
- Kaltim Post uses WordPress search on borneo24.com
- Bali Post supports latest mode via homepage only; search endpoint returns cached empty page
- Harian Jogja uses custom CMS search across multiple subdomains
- SWA uses SvelteKit CMS, server-rendered search
- BeritaSatu uses custom CMS with Chrome UA required for 403 bypass
- KBR uses Next.js SSR, `/articles/indeks` for latest
- All new portals passed strict keyword search validation where applicable
- All new portals passed latest-mode live smoke testing
- Coherence audit fixed keyword filtering bug, content cleanup regex, missing error logs, pagination support, and import order across new scrapers

## [0.8.1] - 2026-05-14

### Added
- Added Pantau.com (`pantau`) scraper with search and latest support
- Added VOI.id (`voi`) scraper with search and latest support
- Total stable scrapers: 42

### Notes
- Pantau.com uses Next.js `__NEXT_DATA__` parsing with `/search?q=` endpoint
- VOI.id uses `/en/artikel/cari?q=` endpoint with HTML parsing and JSON-LD metadata
- Both portals passed strict keyword search validation (zero results for nonsense keywords)
- Both portals passed latest-mode live smoke testing

## [0.8.0] - 2026-05-01

## What's Changed

### Added
- Added `search` and `latest` retrieval methods in the CLI and Python API
- Added latest monitoring helpers: `latest()`, `latest_to_dataframe()`, and `latest_to_file()`
- Added `--limit` and `--max-pages` controls for latest collection volume
- Added per-scraper timeout/error isolation with `--scraper-timeout`
- Added CLI progress logging with `--progress`
- Added newline-delimited JSON output via `--output_format jsonl`
- Added `--time-range` filtering for collected/output articles
- Added `--dedup-file` support for skipping known links and recording emitted links

### Changed
- Search remains the default retrieval method for backward compatibility
- Registry metadata now tracks whether each scraper supports search and latest modes
- Latest mode is now implemented for all 40 stable registered scrapers
- API and CLI limit handling now stops producers/consumers once the requested limit is reached

### Fixed
- Fixed Kontan latest URL normalization for relative and protocol-relative links
- Fixed RRI latest pagination to avoid invalid page requests
- Fixed latest-mode cancellation edge cases that could leak task cancellation errors

### Quality
- Added regression tests for latest support coverage across stable scrapers
- Added CLI/API tests for `latest`, `limit`, `max_pages`, `scraper_timeout`, and progress flags
- Added targeted scraper regression tests for Kontan and RRI latest behavior

### Notes
- Package version metadata is `0.8.0` for this release
- Some sources may still be environment-sensitive because of anti-bot protection, rate limits, geolocation, JavaScript rendering, or source-side changes

**Full Changelog**: https://github.com/okkymabruri/news-watch/compare/v0.7.0...v0.8.0

## [0.7.0] - 2026-04-25

## What's Changed

## Highlights
- Added new stable scrapers: `bbc`, `beritajatim`, `pikiranrakyat`, `poskota`, `rmid`, `suaramerdeka`, `jpnn`, `surabayapagi`, `galamedia`
- Moved scraper loading to the central registry-driven runtime
- Reworked `jpnn`, `surabayapagi`, and `galamedia` for the current strict-search flow
- Aligned recovered scrapers with `dev/SCRAPER_TEMPLATE.md` patterns

## Quality
- Recovered `pikiranrakyat` via Playwright CSE after Cloudflare 1015 blocks
- Fixed `poskota` with URL-date prefiltering to skip archived 404s
- Fixed `rmid` with title filtering and `div.content-berita` extraction
- Fixed `suaramerdeka` with `content_PublishedDate` meta extraction
- Added `ruff` to the dev toolchain and updated `Makefile` lint/test commands to use dev extras
- Marked environment-sensitive CI sources in Linux minimal checks: `jakartapost`, `jawapos`, `kumparan`, `pikiranrakyat`, `suara`, `surabayapagi`, `tirto`

## Notes
- Stable supported scraper set is now 40 sources
- Some scrapers may work locally but fail on remote servers, Linux CI, or GitHub Actions because of anti-bot protection, rate limits, geolocation, JavaScript rendering differences, or source-side changes
- Docs and README were synced to the current runtime state

**Full Changelog**: https://github.com/okkymabruri/news-watch/compare/v0.6.0...v0.7.0

## [0.6.0] - 2026-04-18

### Added
- New supported scrapers: SINDOnews, TVOne, iNews
- Negative nonsense-keyword tests to verify strict keyword-search behavior
- Positive relevance and duplicate-link validation for scraper quality checks

### Changed
- Katadata now uses a public search API and no longer depends on Playwright/browser token capture
- Development dependencies updated to `pytest 9.0.3` and `pytest-asyncio 1.3.0`
- Scraper acceptance policy now requires strict true keyword search for supported sources

### Fixed
- Bisnis fallback logic and keyword relevance handling
- SINDOnews duplicate pagination handling
- TVOne result URL filtering
- README and scraper list consistency across runtime and docs

### Documentation
- Updated docs and notebooks to reflect the 26 supported scrapers and current caveats
- Added release notes for quarantined sources (`jakartapost`, `investor`, `tvrinews`, `rri`)

## [0.5.0] - 2026-01-24

### Added
- New scrapers: IDN Times, Kumparan, Merdeka, Republika, Suara, Tirto
- CSV output hardening: write to a temporary file and rename to final output
- Regression test for CSV quoting/newline handling

### Changed
- HTTP fetching now uses a global fallback chain: aiohttp  rnet  Playwright
- Scraper network tests refactored for Linux/CI stability (explicit exclusions + reduced flakiness)

### Fixed
- Improved cancellation/shutdown behavior to avoid lingering processes in long runs
- Multiple scraper reliability fixes and parsing hardening across the new sources

### Documentation
- Updated docs/README to reflect the expanded scraper coverage and troubleshooting guidance

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
