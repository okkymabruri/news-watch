## Project

`news-watch` is a Python package that aggregates headlines from Indonesian (and a few regional) news sources.
It exposes a CLI and library API; scrapers are pluggable and discovered through a central registry.

Key commands:

- `uv sync --extra dev` — install runtime + dev dependencies.
- `uv run newswatch --help` — CLI entry point.
- `pytest` — unit tests (default CI run).
- `ruff check` — lint.

## Layout

```
src/newswatch/
  api.py            # public API surface
  cli.py            # argparse CLI
  config.py         # runtime config / env
  health.py         # smoke probe helpers
  main.py           # scraper orchestration loop
  models.py         # dataclasses (article, scrape result)
  registry.py       # scraper registry (single source of truth)
  exceptions.py     # custom exception types
  utils.py          # shared helpers (text, http, etc.)
  scrapers/         # one module per source (basescraper.py + adapters)
tests/              # pytest suite, mirrors src/ layout
scripts/            # release notes, recovery probes, version bump helpers
docs/               # markdown reference (architecture, guide, troubleshooting)
dev/                # LOCAL-ONLY scratch notes, scratch sheets, comparisons
notebook/           # ipynb exploration notebooks (Colab-friendly)
```

## Test markers

- `network` — live scraper probes against real sites. Slow, flaked-prone, advisory. Excluded from default CI; run with `pytest -m network` when validating a source by hand.
- All other tests run in the default CI matrix.

## Registry

`src/newswatch/registry.py` is the single source of truth for scrapers.

Adding a new source = add a `ScraperEntry` in `_SCRAPER_ENTRIES` (do not edit files under `src/newswatch/scrapers/` to register a source).

`ScraperEntry` fields:

| field | meaning |
|---|---|
| `slug` | stable identifier used in CLI / API |
| `name` | human-readable label |
| `module` | module path under `newswatch.scrapers` |
| `class_name` | class implementing the source |
| `concurrency` | max parallel requests for this source |
| `status` | `stable` \| `quarantined` \| `investigating` |
| `strict_search` | fail the source if search returns no results |
| `browser_required` | needs a real browser (playwright); not pure HTTP |
| `smoke_keyword` | keyword used by health probes to validate the source |
| `supports_search` | keyword search mode |
| `supports_latest` | "latest headlines" mode |
| `note` | free-form remark for quarantined/investigating entries |

## Hard rules

- Never commit to `main`. Branch off `main`, work on a feature branch, open a PR.
- Never edit files under `src/newswatch/scrapers/` to add a new source. Add the `ScraperEntry` to `src/newswatch/registry.py` instead — the scraper module under `scrapers/` carries only the fetch/parse logic.
- `.omp/` and `dev/` are local-only artifacts (agent handoff scratch, developer notes). Never commit them.
- New dependencies go through `uv add`; do not hand-edit `pyproject.toml` for deps.

## Reference

User-level workflow conventions live in `~/.claude/CLAUDE.md` (general agent guidance, prototype-to-production philosophy, style rules). Project-specific rules live here.
