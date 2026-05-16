"""
Central scraper registry — single source of truth for all news sources.

Each entry declares:
  - slug: unique identifier used in CLI and API
  - name: human-readable display name
  - module: python module name (relative to scrapers/)
  - class_name: scraper class name
  - concurrency: default worker count
  - status: "stable" | "quarantined" | "investigating"
  - strict_search: whether true arbitrary-keyword search is validated
  - browser_required: whether Playwright is needed for this source
  - smoke_keyword: best keyword for smoke tests (defaults to "ihsg")
  - supports_search: whether search mode is supported
  - supports_latest: whether latest mode is supported
  - note: free-text context for devs

Registry is built from a tuple of ScraperEntry via build_registry().
This prevents silent duplicate-key overwrites that raw dict literals allow.
"""

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Data model ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScraperEntry:
    slug: str
    name: str
    module: str
    class_name: str
    concurrency: int = 5
    status: str = "stable"  # stable | quarantined | investigating
    strict_search: bool = True
    browser_required: bool = False
    smoke_keyword: str = "ihsg"
    supports_search: bool = True
    supports_latest: bool = False
    note: str = ""


# ── Entry list (not a dict — dicts silently overwrite duplicate keys) ─────────

_SCRAPER_ENTRIES: Tuple[ScraperEntry, ...] = (
    # ── Stable scrapers ──────────────────────────────────────────────────────
    ScraperEntry(
        "antaranews",
        "Antara News",
        "antaranews", "AntaranewsScraper",
        concurrency=7,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    ScraperEntry(
        "bbc", "BBC News", "bbc", "BBCNewsScraper", smoke_keyword="election", supports_latest=True
    ),
    ScraperEntry(
        "beritajatim",
        "Berita Jatim",
        "beritajatim", "BeritaJatimScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} endpoint; 2026-04-24",
        supports_latest=True,
    ),
    ScraperEntry(
        "bisnis",
        "Bisnis.com",
        "bisnis", "BisnisScraper",
        smoke_keyword="ihsg",
        browser_required=True,
        supports_latest=True,
    ),
    ScraperEntry(
        "bloombergtechnoz",
        "Bloomberg Technoz",
        "bloombergtechnoz", "BloombergTechnozScraper",
        smoke_keyword="teknologi",
        supports_latest=True,
    ),
    ScraperEntry(
        "cnbcindonesia",
        "CNBC Indonesia",
        "cnbcindonesia", "CNBCScraper",
        smoke_keyword="ekonomi",
        supports_latest=True,
    ),
    ScraperEntry(
        "cnnindonesia",
        "CNN Indonesia",
        "cnnindonesia", "CNNIndonesiaScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ihsg",
        note="promoted to stable; rebuilt with RSS keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "detik",
        "Detik",
        "detik", "DetikScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "galamedia",
        "Galamedia",
        "galamedia", "GalamediaScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint + div.latest__item + keyword-in-title filtering; 2026-04-24",
        supports_latest=True,
    ),
    ScraperEntry(
        "idntimes",
        "IDN Times",
        "idntimes", "IDNTimesScraper",
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ihsg",
        note="promoted to stable; rebuilt with Playwright tag page + keyword URL filter; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry("inews", "iNews", "inews", "INewsScraper", smoke_keyword="ihsg", supports_latest=True),
    ScraperEntry(
        "investor",
        "Investor.id",
        "investor", "InvestorScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ihsg",
        note="promoted to stable; no-result gate added 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "jakartapost",
        "The Jakarta Post",
        "jakartapost", "JakartaPostScraper",
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="indonesia",
        note="rebuilt with Playwright CSE bootstrap; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "jawapos", "Jawa Pos", "jawapos", "JawaposScraper", smoke_keyword="ihsg", supports_latest=True
    ),
    ScraperEntry(
        "jpnn",
        "JPNN (Jawa Pos News Network)",
        "jpnn", "JpnnScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} + meta[name=jpnncom_news_pubdate] date extraction; 2026-04-24",
        supports_latest=True,
    ),
    ScraperEntry(
        "katadata", "Katadata", "katadata", "KatadataScraper", smoke_keyword="ihsg", supports_latest=True
    ),
    ScraperEntry(
        "kompas",
        "Kompas",
        "kompas", "KompasScraper",
        concurrency=7,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    ScraperEntry(
        "kontan",
        "Kontan",
        "kontan", "KontanScraper",
        smoke_keyword="ihsg",
        note="max 50 pages",
        supports_latest=True,
    ),
    ScraperEntry(
        "kumparan",
        "Kumparan",
        "kumparan", "KumparanScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "liputan6",
        "Liputan6",
        "liputan6", "Liputan6Scraper",
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ihsg",
        note="promoted to stable; rebuilt with Playwright tag page + keyword URL filter; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "mediaindonesia",
        "Media Indonesia",
        "mediaindonesia", "MediaIndonesiaScraper",
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    ScraperEntry(
        "merdeka",
        "Merdeka",
        "merdeka", "MerdekaScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with RSS keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "metrotvnews",
        "MetroTV News",
        "metrotvnews", "MetrotvnewsScraper",
        concurrency=2,
        smoke_keyword="prabowo",
        note="flaky for finance terms",
        supports_latest=True,
    ),
    ScraperEntry(
        "mongabay",
        "Mongabay Indonesia",
        "mongabay", "MongabayScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="deforestasi",
        note="promoted to stable; WordPress REST API /wp-json/wp/v2/posts?search=; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "okezone",
        "Okezone",
        "okezone", "OkezoneScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ihsg",
        note="promoted to stable; rebuilt with /tag/{keyword} endpoint; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "pantau",
        "Pantau.com",
        "pantau", "PantauScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint + Next.js __NEXT_DATA__ parsing; 2026-05-13",
        supports_latest=True,
    ),
    ScraperEntry(
        "pikiranrakyat",
        "Pikiran Rakyat",
        "pikiranrakyat", "PikiranRakyatScraper",
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; Playwright CSE bypass CF 1015; 2026-04-23",
        supports_latest=True,
    ),
    ScraperEntry(
        "poskota",
        "Poskota",
        "poskota", "PoskotaScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} endpoint with URL date pre-filter; 2026-04-23",
        supports_latest=True,
    ),
    ScraperEntry(
        "republika",
        "Republika",
        "republika", "RepublikaScraper",
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with Playwright tag page + keyword URL filter; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "rri",
        "RRI (RRI.co.id)",
        "rri", "RRIScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint with plain HTTP; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "rmid",
        "RM.ID (Rakyat Merdeka)",
        "rmid", "RmidScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /?s= search + title filtering + div.content-berita; 2026-04-23",
        supports_latest=True,
    ),
    ScraperEntry(
        "sindonews",
        "SINDOnews",
        "sindonews", "SindonewsScraper",
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    ScraperEntry(
        "suara",
        "Suara",
        "suara", "SuaraScraper",
        concurrency=12,
        smoke_keyword="prabowo",
        browser_required=True,
        supports_latest=True,
    ),
    ScraperEntry(
        "suaramerdeka",
        "Suara Merdeka",
        "suaramerdeka", "SuaraMerdekaScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint with content_PublishedDate; 2026-04-23",
        supports_latest=True,
    ),
    ScraperEntry(
        "surabayapagi",
        "Surabaya Pagi",
        "surabayapagi", "SurabayaPagiScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} + article:published_time; concurrency=3 for rate limiting; 2026-04-24",
        supports_latest=True,
    ),
    ScraperEntry(
        "swa",
        "SWA",
        "swa", "SWAScraper",
        status="stable",
        strict_search=True,
        concurrency=5,
        supports_latest=True,
    ),
    ScraperEntry("tempo", "Tempo", "tempo", "TempoScraper", smoke_keyword="ihsg", supports_latest=True),
    ScraperEntry(
        "tirto",
        "Tirto",
        "tirto", "TirtoScraper",
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="prabowo",
        note="promoted to stable; rebuilt with Playwright CSE capture; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "tribunnews",
        "Tribunnews",
        "tribunnews", "TribunnewsScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-23",
        supports_latest=True,
    ),
    ScraperEntry(
        "tvone", "TVOne", "tvone", "TVOneScraper", smoke_keyword="ekonomi", supports_latest=True
    ),
    ScraperEntry(
        "tvrinews",
        "TVRI News",
        "tvrinews", "TVRINewsScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    ScraperEntry(
        "viva",
        "Viva",
        "viva", "VivaScraper",
        concurrency=7,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    ScraperEntry(
        "voi",
        "VOI.id",
        "voi", "VOIScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /en/artikel/cari?q= endpoint + HTML parsing; 2026-05-13",
        supports_latest=True,
    ),
    # ── New batch: 2026-05-batch2 ────────────────────────────────────────────
    ScraperEntry(
        "voaindonesia",
        "VOA Indonesia",
        "voaindonesia", "VOAIndonesiaScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /s?k= endpoint + HTML parsing; 2026-05-15",
        supports_latest=True,
    ),
    ScraperEntry(
        "balipost",
        "Bali Post",
        "balipost", "BaliPostScraper",
        status="stable",
        strict_search=False,
        smoke_keyword="ekonomi",
        note="new; latest-only via homepage; WordPress /search?q= returns empty cached page; 2026-05-15",
        supports_search=False,
        supports_latest=True,
    ),
    ScraperEntry(
        "dailysocial",
        "DailySocial",
        "dailysocial", "DailySocialScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; WordPress /?s= search + wp-block-post containers; 2026-05-15",
        supports_latest=True,
    ),
    ScraperEntry(
        "gatra",
        "Gatra",
        "gatra", "GatraScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; WordPress /?s= search + title keyword filtering (search returns all); 2026-05-15",
        supports_latest=True,
    ),
    ScraperEntry(
        "kaltimpost",
        "Kaltim Post (Borneo24)",
        "kaltimpost", "KaltimPostScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; WordPress /?s= search + path-based article filtering; 2026-05-15",
        supports_latest=True,
    ),
    ScraperEntry(
        "projectmultatuli",
        "Project Multatuli",
        "projectmultatuli", "ProjectMultatuliScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; Elementor /en/search/{keyword} + e-loop-item containers; 2026-05-15",
        supports_latest=True,
    ),
    ScraperEntry(
        "harianjogja",
        "Harian Jogja",
        "harianjogja", "HarianJogjaScraper",
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; custom CMS /search?q= endpoint; r-{id} URL pattern; 2026-05-16",
        supports_latest=True,
    ),
    ScraperEntry(
        "kbr",
        "KBR",
        "kbr", "KBRScraper",
        status="stable",
        strict_search=True,
        concurrency=5,
        smoke_keyword="ekonomi",
        note="new; Next.js 14+ App Router /search?q= endpoint; /articles/indeks for latest; 2026-05-16",
        supports_latest=True,
    ),
    ScraperEntry(
        "beritasatu",
        "BeritaSatu",
        "beritasatu", "BeritaSatuScraper",
        status="stable",
        strict_search=True,
        concurrency=5,
        smoke_keyword="ekonomi",
        supports_latest=True,
        note="new; custom CMS /search/{keyword} path param; Chrome UA required; 2026-05-16",
    ),
)


# ── Registry builder with guardrails ─────────────────────────────────────────


def build_registry(entries: Tuple[ScraperEntry, ...]) -> Dict[str, ScraperEntry]:
    """Build SCRAPERS dict from entry tuple with duplicate/consistency checks.

    Raises ValueError on:
    - duplicate slug
    - duplicate module
    - duplicate class_name
    - supports_search=False with strict_search=True
    """
    seen_slugs: set = set()
    seen_modules: set = set()
    seen_classes: set = set()
    result: Dict[str, ScraperEntry] = {}

    for e in entries:
        if e.slug in seen_slugs:
            raise ValueError(f"Duplicate scraper slug: '{e.slug}'")
        if e.module in seen_modules:
            raise ValueError(f"Duplicate scraper module: '{e.module}'")
        if e.class_name in seen_classes:
            raise ValueError(f"Duplicate scraper class_name: '{e.class_name}'")
        if not e.supports_search and e.strict_search:
            raise ValueError(
                f"Scraper '{e.slug}' has strict_search=True but supports_search=False. "
                "Set strict_search=False when search is unsupported."
            )
        seen_slugs.add(e.slug)
        seen_modules.add(e.module)
        seen_classes.add(e.class_name)
        result[e.slug] = e

    return result


SCRAPERS: Dict[str, ScraperEntry] = build_registry(_SCRAPER_ENTRIES)


# ── Runtime validation ───────────────────────────────────────────────────────

_SCRAPER_IGNORE = {"__init__", "basescraper"}


def validate_registry() -> List[str]:
    """Validate registry integrity. Returns list of issues (empty = OK)."""
    issues: List[str] = []

    # Check all registry modules have files
    scraper_dir = Path(__file__).parent / "scrapers"
    registry_modules = {e.module for e in _SCRAPER_ENTRIES}

    for mod in sorted(registry_modules):
        if not (scraper_dir / f"{mod}.py").exists():
            issues.append(f"Registry module '{mod}' has no file at scrapers/{mod}.py")

    # Check all scraper files have registry entries
    file_modules = {
        p.stem for p in scraper_dir.glob("*.py") if p.stem not in _SCRAPER_IGNORE
    }
    orphan_files = file_modules - registry_modules
    for f in sorted(orphan_files):
        issues.append(f"Scraper file '{f}.py' has no registry entry")

    # Check all registry classes import
    for slug, entry in SCRAPERS.items():
        try:
            mod = importlib.import_module(
                f".scrapers.{entry.module}", package="newswatch"
            )
            if not hasattr(mod, entry.class_name):
                issues.append(
                    f"Scraper '{slug}': class '{entry.class_name}' not found in module"
                )
        except ImportError as e:
            issues.append(f"Scraper '{slug}': module import failed — {e}")

    return issues


# ── Convenience functions ────────────────────────────────────────────────────


def get_stable_scrapers() -> Dict[str, ScraperEntry]:
    """Return only scrapers with status 'stable'."""
    return {k: v for k, v in SCRAPERS.items() if v.status == "stable"}


def get_search_scrapers() -> Dict[str, ScraperEntry]:
    """Return stable scrapers that support search mode."""
    return {k: v for k, v in get_stable_scrapers().items() if v.supports_search}


def get_latest_scrapers() -> Dict[str, ScraperEntry]:
    """Return stable scrapers that support latest mode."""
    return {k: v for k, v in get_stable_scrapers().items() if v.supports_latest}


def get_quarantined_scrapers() -> Dict[str, ScraperEntry]:
    """Return scrapers that are quarantined."""
    return {k: v for k, v in SCRAPERS.items() if v.status == "quarantined"}


def get_investigating_scrapers() -> Dict[str, ScraperEntry]:
    """Return scrapers under active investigation."""
    return {k: v for k, v in SCRAPERS.items() if v.status == "investigating"}


def get_scraper_by_slug(slug: str) -> Optional[ScraperEntry]:
    """Look up a single scraper by its slug."""
    return SCRAPERS.get(slug)


def get_stable_slugs() -> List[str]:
    """Return sorted list of stable scraper slugs."""
    return sorted(get_stable_scrapers().keys())


def get_all_slugs() -> List[str]:
    """Return sorted list of all scraper slugs."""
    return sorted(SCRAPERS.keys())


def get_available_scrapers_from_registry(method: str = "search"):
    """Build the scraper_classes dict for main.py from the registry.

    Returns:
        tuple: (scraper_classes_dict, linux_excluded_scrapers_dict)
        scraper_classes maps slug -> {"class": ScraperClass, "params": {"concurrency": N}}
    """
    scraper_classes = {}
    linux_excluded = {}

    if method == "latest":
        entries = get_latest_scrapers()
    else:
        entries = get_search_scrapers()

    for slug, entry in entries.items():
        try:
            module = importlib.import_module(
                f".scrapers.{entry.module}", package="newswatch"
            )
            scraper_class = getattr(module, entry.class_name)
            scraper_classes[slug] = {
                "class": scraper_class,
                "params": {"concurrency": entry.concurrency}
                if entry.concurrency
                else {},
            }
        except (ImportError, AttributeError) as e:
            logging.warning(f"Failed to load scraper '{slug}': {e}")

    return scraper_classes, linux_excluded
