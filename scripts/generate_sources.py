#!/usr/bin/env python3
"""Registry-driven source doc generator.

Reads ``newswatch.registry.SCRAPERS``, computes counts, and rewrites marked
regions in README.md + ``docs/*.md``. Markers look like::

    <!-- BEGIN GENERATED: <id> -->
    ...content...
    <!-- END GENERATED: <id> -->

Run with ``--check`` to fail (exit 1) if any marked block is out of date.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Curated slug → homepage URL mapping. Source of truth: the reviewed main
# README's source list. Keys MUST equal registry slugs; renderers validate
# this on every run so a stale mapping fails fast instead of silently
# dropping a source link.
SOURCE_URLS: Dict[str, str] = {
    "alinea": "https://www.alinea.id",
    "antaranews": "https://antaranews.com",
    "apnews": "https://apnews.com",
    "aljazeera": "https://www.aljazeera.com",
    "betahita": "https://www.betahita.id",
    "balipost": "https://www.balipost.com",
    "bantennews": "https://www.bantennews.co.id",
    "bbc": "https://bbc.com",
    "beritajatim": "https://beritajatim.com",
    "beritasatu": "https://www.beritasatu.com",
    "bisnis": "https://bisnis.com",
    "bloombergtechnoz": "https://bloombergtechnoz.com",
    "cnaindonesia": "https://www.cna.id",
    "cnbcindonesia": "https://cnbcindonesia.com",
    "conversationid": "https://theconversation.com/id",
    "cnnindonesia": "https://cnnindonesia.com",
    "dandapala": "https://dandapala.com",
    "ddtcnews": "https://news.ddtc.co.id",
    "dailysocial": "https://news.dailysocial.id",
    "detik": "https://detik.com",
    "fajar": "https://fajar.co.id",
    "galamedia": "https://galamedia.pikiran-rakyat.com",
    "gatra": "https://www.gatra.net",
    "gnfi": "https://www.goodnewsfromindonesia.id",
    "grid": "https://www.grid.id",
    "harianjogja": "https://www.harianjogja.com",
    "hipwee": "https://www.hipwee.com",
    "independen": "https://independen.id",
    "idxchannel": "https://www.idxchannel.com",
    "infobanknews": "https://infobanknews.com",
    "indopolitika": "https://indopolitika.com",
    "idnfinancials": "https://www.idnfinancials.com/id/",
    "idntimes": "https://idntimes.com",
    "inews": "https://inews.id",
    "investor": "https://investor.id",
    "jakartaglobe": "https://jakartaglobe.id",
    "jakartapost": "https://thejakartapost.com",
    "jakartaselarascoid": "https://jakarta.selaras.co.id",
    "jawapos": "https://jawapos.com",
    "hukumonline": "https://www.hukumonline.com",
    "jpnn": "https://jpnn.com",
    "kaltimpost": "https://kaltimkece.borneo24.com",
    "katadata": "https://katadata.co.id",
    "kbr": "https://kbr.id",
    "kompas": "https://kompas.com",
    "kontan": "https://kontan.co.id",
    "kumparan": "https://kumparan.com",
    "liputan6": "https://liputan6.com",
    "mediaindonesia": "https://mediaindonesia.com",
    "merdeka": "https://merdeka.com",
    "metrotvnews": "https://metrotvnews.com",
    "niagaasia": "https://www.niaga.asia",
    "mojok": "https://mojok.co",
    "mongabay": "https://mongabay.co.id",
    "nusabali": "https://www.nusabali.com",
    "okezone": "https://okezone.com",
    "pantau": "https://www.pantau.com",
    "pikiranrakyat": "https://pikiran-rakyat.com",
    "poskota": "https://poskota.co.id",
    "projectmultatuli": "https://projectmultatuli.org",
    "republika": "https://republika.co.id",
    "rmid": "https://rm.id",
    "rri": "https://rri.co.id",
    "rmol": "https://rmol.id",
    "sindonews": "https://sindonews.com",
    "suara": "https://suara.com",
    "suaramerdeka": "https://suaramerdeka.com",
    "surabayapagi": "https://surabayapagi.com",
    "swa": "https://swa.co.id",
    "tempo": "https://tempo.co",
    "tirto": "https://tirto.id",
    "tribunnews": "https://tribunnews.com",
    "tvone": "https://tvonenews.com",
    "tvrinews": "https://tvrinews.id",
    "voi": "https://voi.id",
    "wartaekonomi": "https://wartaekonomi.co.id",
    "voaindonesia": "https://voaindonesia.com",
    "viva": "https://viva.co.id",
}


def get_source_url_map() -> Dict[str, str]:
    """Return the curated slug → URL mapping.

    Kept as a function (rather than reading ``SOURCE_URLS`` directly) so
    tests can monkeypatch the mapping without mutating module state.
    """
    return dict(SOURCE_URLS)


# ── Stats ──────────────────────────────────────────────────────────────────


def _load_registry():
    """Load newswatch.registry as a module and return it.

    Module loading is the slow step; cached after the first call so the
    source renderer doesn't re-parse the file on every block.
    """
    cached = getattr(_load_registry, "_module", None)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "newswatch.registry",
        REPO_ROOT / "src" / "newswatch" / "registry.py",
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load newswatch.registry")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _load_registry._module = module  # type: ignore[attr-defined]
    return module


def compute_stats() -> Dict[str, int]:
    """Return registered, stable, and status counts from the registry.

    Exposes both registered capability counts (every slug in the registry)
    and stable-release counts (status == "stable") so renderers can pick
    the right view for each block. Counts for investigating and quarantined
    statuses are always explicit — renderers describe them dynamically so
    the docs never claim "none" when those counts are nonzero.

    Keys:
      registered_total, registered_search, registered_latest — every slug.
      stable_total, stable_search, stable_latest — status == "stable".
      investigating, quarantined — counts of non-stable statuses.

    Only uses fields that exist on ``ScraperEntry``: ``status``,
    ``supports_search``, ``supports_latest``.
    """
    scrapers = _load_registry().SCRAPERS

    registered_total = len(scrapers)
    registered_search = sum(1 for s in scrapers.values() if s.supports_search)
    registered_latest = sum(1 for s in scrapers.values() if s.supports_latest)
    stable_total = sum(1 for s in scrapers.values() if s.status == "stable")
    stable_search = sum(
        1 for s in scrapers.values() if s.status == "stable" and s.supports_search
    )
    stable_latest = sum(
        1 for s in scrapers.values() if s.status == "stable" and s.supports_latest
    )
    quarantined = sum(1 for s in scrapers.values() if s.status == "quarantined")
    investigating = sum(
        1 for s in scrapers.values() if s.status == "investigating"
    )
    return {
        "registered_total": registered_total,
        "registered_search": registered_search,
        "registered_latest": registered_latest,
        "stable_total": stable_total,
        "stable_search": stable_search,
        "stable_latest": stable_latest,
        "quarantined": quarantined,
        "investigating": investigating,
    }


def validate_source_url_map(mapping: Dict[str, str]) -> None:
    """Raise ``ValueError`` when source URLs drift from the registry."""
    registry_slugs = set(_load_registry().SCRAPERS.keys())
    mapping_slugs = set(mapping.keys())
    missing = sorted(registry_slugs - mapping_slugs)
    extra = sorted(mapping_slugs - registry_slugs)
    url_counts = {url: list(mapping.values()).count(url) for url in mapping.values()}
    duplicate_urls = sorted(url for url, count in url_counts.items() if count > 1)
    problems: List[str] = []
    if missing:
        problems.append(f"missing from mapping: {missing}")
    if extra:
        problems.append(f"present in mapping but not in registry: {extra}")
    if duplicate_urls:
        problems.append(f"duplicate URLs: {duplicate_urls}")
    if problems:
        raise ValueError("source URL mapping drift: " + "; ".join(problems))


# ── Renderers ──────────────────────────────────────────────────────────────


def _status_summary(stats: Dict[str, int]) -> str:
    """Dynamic clause about investigating/quarantined sources.

    Always reflects the current counts — never claims "none" when a
    count is nonzero. Singular/plural noun agrees with the count.
    """
    parts: List[str] = []
    if stats["investigating"]:
        n = stats["investigating"]
        parts.append(f"{n} source{'' if n == 1 else 's'} under investigation")
    if stats["quarantined"]:
        n = stats["quarantined"]
        parts.append(f"{n} source{'' if n == 1 else 's'} quarantined")
    if not parts:
        return "No sources under investigation or quarantined."
    return "; ".join(parts) + "."


def render_readme_heading(stats: Dict[str, int]) -> str:
    """README "Supported Websites" section heading + intro.

    Uses the registered total — every slug in the URL mapping corresponds
    to a registered scraper, regardless of stability status.
    """
    return f"## Supported Websites ({stats['registered_total']})\n"


def render_readme_sources(stats: Dict[str, int]) -> str:
    """README linked source list, one ``[name](url)`` per registry slug.

    Rendering is deterministic: slugs are sorted alphabetically before being
    joined with the comma-newline that matches main's prior list format.
    The URL mapping is validated against the registry on every call so a
    stale or rogue slug raises ``ValueError`` instead of producing a
    silently-broken README.
    """
    url_map = get_source_url_map()
    validate_source_url_map(url_map)
    registry = _load_registry().SCRAPERS
    lines = [f"[{registry[slug].name}]({url_map[slug]})" for slug in sorted(url_map)]
    return ",\n".join(lines) + "\n"


def render_readme_counts(stats: Dict[str, int]) -> str:
    """README bullets summarizing registered, stable, and status counts."""
    state = _status_summary(stats)
    lines = [
        "> **Notes:**",
        f"> - {stats['registered_total']} registered sources: "
        f"{stats['registered_search']} with keyword search, "
        f"{stats['registered_latest']} with latest mode.",
        f"> - {stats['stable_total']} stable scrapers in the current release: "
        f"{stats['stable_search']} with keyword search, "
        f"{stats['stable_latest']} with latest mode.",
        f"> - {state}",
        "> - AP News uses topic hub pages with keyword-in-title filtering "
        "(robots disallows /search?q=*).",
        "> - Al Jazeera is latest-only via RSS feed (search page is JS-rendered).",
        "> - Reuters skipped (WAF blocked).",
        "> - Use `-s all` to force-run all scrapers (may cause errors/timeouts).",
        "> - Some sources are environment-sensitive and may fail on remote "
        "servers even if they work locally.",
        "> - Limitation: Kontan scraper maximum 50 pages.",
    ]
    return "\n".join(lines) + "\n"


def render_architecture_state(stats: Dict[str, int]) -> str:
    """docs/architecture.md "Current State" table."""
    return (
        "## Current State\n"
        "\n"
        "| State | Count |\n"
        "|---|---|\n"
        f"| registered | {stats['registered_total']} |\n"
        f"| stable | {stats['stable_total']} |\n"
        f"| quarantined | {stats['quarantined']} |\n"
        f"| investigating | {stats['investigating']} |\n"
    )


def render_index_summary(stats: Dict[str, int]) -> str:
    """docs/index.md intro paragraph."""
    return (
        "news-watch scrapes structured news data from Indonesia's top news "
        "websites with keyword/date search and latest-news monitoring.\n"
        "\n"
        f"The current stable release supports {stats['stable_total']} news "
        f"scrapers ({stats['stable_search']} Indonesian/global sources with "
        f"search mode, {stats['stable_latest']} with latest mode). "
        f"{stats['registered_total']} sources are registered in total: "
        f"{_status_summary(stats)}\n"
    )


def render_api_notes(stats: Dict[str, int]) -> str:
    """docs/api-reference.md stable-API notes block."""
    return (
        "## Stable API Notes\n"
        "\n"
        f"All {stats['registered_total']} registered scrapers are exposed via "
        "`list_scrapers()` and the public `SCRAPERS` mapping. "
        f"{stats['registered_search']} of them support the `search` method; "
        f"all {stats['registered_latest']} support `latest`.\n"
        "\n"
        "## Notes\n"
        "\n"
        "- Prefer `scrapers=\"auto\"` unless you know which sites you need.\n"
        "- Cloud/server environments are more likely to be blocked.\n"
        f"- Stable support currently covers {stats['stable_total']} scrapers "
        f"({stats['stable_search']} search-capable, {stats['stable_latest']} "
        "latest-capable).\n"
        f"- {_status_summary(stats)}\n"
        "\n"
        "**Empty results**: Check if your keywords are in Indonesian or try "
        "broader terms.\n"
    )


def render_guide_counts(stats: Dict[str, int]) -> str:
    """docs/practical-guide.md choosing-your-sources paragraph."""
    return (
        f"The stable release currently exposes {stats['stable_total']} supported "
        f"scrapers. {_status_summary(stats)}\n"
        "\n"
        f"{stats['stable_search']} of {stats['stable_total']} stable sources support "
        f"keyword search; {stats['stable_latest']} support latest monitoring.\n"
        f"The full registry contains {stats['registered_total']} sources: "
        f"{stats['registered_search']} support keyword search and "
        f"{stats['registered_latest']} support latest monitoring.\n"
    )


# ── Block replacement ──────────────────────────────────────────────────────

# Group 1 = BEGIN line, group 2 = id, group 3 = body, group 4 = END line.
_MARKER_RE = re.compile(
    r"(<!-- BEGIN GENERATED: (?P<id>[A-Za-z0-9_-]+) -->\n)"
    r"(?P<body>.*?)"
    r"(<!-- END GENERATED: (?P=id) -->\n?)",
    re.DOTALL,
)


def render_block(
    text: str, block_id: str, renderer: Callable[[Dict[str, int]], str]
) -> str:
    """Replace the body of the marker block identified by ``block_id``.

    The renderer MUST accept a stats dict and return a string (no trailing
    newline required). The replacement preserves both markers and surrounding
    text exactly.
    """
    stats = compute_stats()

    def _replace(match: re.Match[str]) -> str:
        if match.group("id") != block_id:
            return match.group(0)
        new_body = renderer(stats)
        if not new_body.endswith("\n"):
            new_body += "\n"
        return match.group(1) + new_body + match.group(4)

    new_text, n = _MARKER_RE.subn(_replace, text)
    if n == 0:
        raise KeyError(f"marker block {block_id!r} not found")
    return new_text


# ── Targets ────────────────────────────────────────────────────────────────

TARGETS: List[Tuple[Path, str, Callable[[Dict[str, int]], str]]] = [
    (REPO_ROOT / "README.md", "readme-heading", render_readme_heading),
    (REPO_ROOT / "README.md", "readme-sources", render_readme_sources),
    (REPO_ROOT / "README.md", "readme-counts", render_readme_counts),
    (
        REPO_ROOT / "docs" / "architecture.md",
        "architecture-state",
        render_architecture_state,
    ),
    (REPO_ROOT / "docs" / "index.md", "index-summary", render_index_summary),
    (
        REPO_ROOT / "docs" / "api-reference.md",
        "api-notes",
        render_api_notes,
    ),
    (
        REPO_ROOT / "docs" / "practical-guide.md",
        "guide-counts",
        render_guide_counts,
    ),
]


# ── CLI ────────────────────────────────────────────────────────────────────


def _run(check: bool) -> int:
    drift: List[str] = []
    for path, block_id, renderer in TARGETS:
        original = path.read_text(encoding="utf-8")
        try:
            updated = render_block(original, block_id, renderer)
        except KeyError as exc:
            print(f"{path}: missing marker ({exc})")
            drift.append(f"{path}: missing marker for {block_id}")
            continue
        if updated != original:
            if check:
                drift.append(f"{path}: block {block_id} is out of date")
            else:
                path.write_text(updated, encoding="utf-8")
                print(f"{path}: rewrote block {block_id}")
    if drift:
        print("drift detected:")
        for line in drift:
            print(f"  - {line}")
        return 1
    if check:
        print("all generated blocks are up to date")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any marked block is out of date",
    )
    args = parser.parse_args(argv)
    return _run(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())