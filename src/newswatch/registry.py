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
"""

import importlib
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional


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


# ── Registry ──────────────────────────────────────────────────────────────────

SCRAPERS: Dict[str, ScraperEntry] = {
    # ── Stable scrapers (26 in 0.6.0) ────────────────────────────────────────
    "antaranews": ScraperEntry(
        slug="antaranews",
        name="Antara News",
        module="antaranews",
        class_name="AntaranewsScraper",
        concurrency=7,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "bisnis": ScraperEntry(
        slug="bisnis",
        name="Bisnis.com",
        module="bisnis",
        class_name="BisnisScraper",
        concurrency=5,
        smoke_keyword="ihsg",
        browser_required=True,
        supports_latest=True,
    ),
    "bloombergtechnoz": ScraperEntry(
        slug="bloombergtechnoz",
        name="Bloomberg Technoz",
        module="bloombergtechnoz",
        class_name="BloombergTechnozScraper",
        concurrency=3,
        smoke_keyword="teknologi",
        supports_latest=True,
    ),
    "cnbcindonesia": ScraperEntry(
        slug="cnbcindonesia",
        name="CNBC Indonesia",
        module="cnbcindonesia",
        class_name="CNBCScraper",
        concurrency=5,
        smoke_keyword="ekonomi",
        supports_latest=True,
    ),
    "cnnindonesia": ScraperEntry(
        slug="cnnindonesia",
        name="CNN Indonesia",
        module="cnnindonesia",
        class_name="CNNIndonesiaScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ihsg",
        supports_latest=True,
        note="promoted to stable; rebuilt with RSS keyword filtering; 2026-04-18",
    ),
    "detik": ScraperEntry(
        slug="detik",
        name="Detik",
        module="detik",
        class_name="DetikScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        supports_latest=True,
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-18",
    ),
    "idntimes": ScraperEntry(
        slug="idntimes",
        name="IDN Times",
        module="idntimes",
        class_name="IDNTimesScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ihsg",
        note="promoted to stable; rebuilt with Playwright tag page + keyword URL filter; 2026-04-18",
        supports_latest=True,
    ),
    "inews": ScraperEntry(
        slug="inews",
        name="iNews",
        module="inews",
        class_name="INewsScraper",
        concurrency=5,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "jawapos": ScraperEntry(
        slug="jawapos",
        name="Jawa Pos",
        module="jawapos",
        class_name="JawaposScraper",
        concurrency=5,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "katadata": ScraperEntry(
        slug="katadata",
        name="Katadata",
        module="katadata",
        class_name="KatadataScraper",
        concurrency=5,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "kompas": ScraperEntry(
        slug="kompas",
        name="Kompas",
        module="kompas",
        class_name="KompasScraper",
        concurrency=7,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "kontan": ScraperEntry(
        slug="kontan",
        name="Kontan",
        module="kontan",
        class_name="KontanScraper",
        concurrency=3,
        smoke_keyword="ihsg",
        note="max 50 pages",
        supports_latest=True,
    ),
    "kumparan": ScraperEntry(
        slug="kumparan",
        name="Kumparan",
        module="kumparan",
        class_name="KumparanScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    "liputan6": ScraperEntry(
        slug="liputan6",
        name="Liputan6",
        module="liputan6",
        class_name="Liputan6Scraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ihsg",
        note="promoted to stable; rebuilt with Playwright tag page + keyword URL filter; 2026-04-18",
        supports_latest=True,
    ),
    "mediaindonesia": ScraperEntry(
        slug="mediaindonesia",
        name="Media Indonesia",
        module="mediaindonesia",
        class_name="MediaIndonesiaScraper",
        concurrency=5,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "merdeka": ScraperEntry(
        slug="merdeka",
        name="Merdeka",
        module="merdeka",
        class_name="MerdekaScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with RSS keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    "metrotvnews": ScraperEntry(
        slug="metrotvnews",
        name="MetroTV News",
        module="metrotvnews",
        class_name="MetrotvnewsScraper",
        concurrency=2,
        smoke_keyword="prabowo",
        note="flaky for finance terms",
        supports_latest=True,
    ),
    "okezone": ScraperEntry(
        slug="okezone",
        name="Okezone",
        module="okezone",
        class_name="OkezoneScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ihsg",
        note="promoted to stable; rebuilt with /tag/{keyword} endpoint; 2026-04-18",
        supports_latest=True,
    ),
    "republika": ScraperEntry(
        slug="republika",
        name="Republika",
        module="republika",
        class_name="RepublikaScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with Playwright tag page + keyword URL filter; 2026-04-18",
        supports_latest=True,
    ),
    "sindonews": ScraperEntry(
        slug="sindonews",
        name="SINDOnews",
        module="sindonews",
        class_name="SindonewsScraper",
        concurrency=5,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "suara": ScraperEntry(
        slug="suara",
        name="Suara",
        module="suara",
        class_name="SuaraScraper",
        concurrency=12,
        smoke_keyword="prabowo",
        browser_required=True,
        supports_latest=True,
    ),
    "tempo": ScraperEntry(
        slug="tempo",
        name="Tempo",
        module="tempo",
        class_name="TempoScraper",
        concurrency=1,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    "tirto": ScraperEntry(
        slug="tirto",
        name="Tirto",
        module="tirto",
        class_name="TirtoScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="prabowo",
        note="promoted to stable; rebuilt with Playwright CSE capture; 2026-04-18",
        supports_latest=True,
    ),
    "tribunnews": ScraperEntry(
        slug="tribunnews",
        name="Tribunnews",
        module="tribunnews",
        class_name="TribunnewsScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-23",
        supports_latest=True,
    ),
    "tvone": ScraperEntry(
        slug="tvone",
        name="TVOne",
        module="tvone",
        class_name="TVOneScraper",
        concurrency=5,
        smoke_keyword="ekonomi",
        supports_latest=True,
    ),
    "viva": ScraperEntry(
        slug="viva",
        name="Viva",
        module="viva",
        class_name="VivaScraper",
        concurrency=7,
        smoke_keyword="ihsg",
        supports_latest=True,
    ),
    # ── Quarantined scrapers ─────────────────────────────────────────────────
    "jakartapost": ScraperEntry(
        slug="jakartapost",
        name="The Jakarta Post",
        module="jakartapost",
        class_name="JakartaPostScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="indonesia",
        note="rebuilt with Playwright CSE bootstrap; 2026-04-18",
        supports_latest=True,
    ),
    "investor": ScraperEntry(
        slug="investor",
        name="Investor.id",
        module="investor",
        class_name="InvestorScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ihsg",
        note="promoted to stable; no-result gate added 2026-04-18",
        supports_latest=True,
    ),
    "tvrinews": ScraperEntry(
        slug="tvrinews",
        name="TVRI News",
        module="tvrinews",
        class_name="TVRINewsScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; rebuilt with sitemap keyword filtering; 2026-04-18",
        supports_latest=True,
    ),
    # ── Investigating / new targets ──────────────────────────────────────────
    "pikiranrakyat": ScraperEntry(
        slug="pikiranrakyat",
        name="Pikiran Rakyat",
        module="pikiranrakyat",
        class_name="PikiranRakyatScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        browser_required=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; Playwright CSE bypass CF 1015; 2026-04-23",
        supports_latest=True,
    ),
    "poskota": ScraperEntry(
        slug="poskota",
        name="Poskota",
        module="poskota",
        class_name="PoskotaScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} endpoint with URL date pre-filter; 2026-04-23",
        supports_latest=True,
    ),
    "rmid": ScraperEntry(
        slug="rmid",
        name="RM.ID (Rakyat Merdeka)",
        module="rmid",
        class_name="RmidScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /?s= search + title filtering + div.content-berita; 2026-04-23",
        supports_latest=True,
    ),
    "suaramerdeka": ScraperEntry(
        slug="suaramerdeka",
        name="Suara Merdeka",
        module="suaramerdeka",
        class_name="SuaraMerdekaScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint with content_PublishedDate; 2026-04-23",
        supports_latest=True,
    ),
    "bbc": ScraperEntry(
        slug="bbc",
        name="BBC News",
        module="bbc",
        class_name="BBCNewsScraper",
        concurrency=5,
        smoke_keyword="election",
        supports_latest=True,
    ),
    "mongabay": ScraperEntry(
        slug="mongabay",
        name="Mongabay Indonesia",
        module="mongabay",
        class_name="MongabayScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="deforestasi",
        note="promoted to stable; WordPress REST API /wp-json/wp/v2/posts?search=; 2026-04-18",
        supports_latest=True,
    ),
    "beritajatim": ScraperEntry(
        slug="beritajatim",
        name="Berita Jatim",
        module="beritajatim",
        class_name="BeritaJatimScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} endpoint; 2026-04-24",
        supports_latest=True,
    ),
    "pantau": ScraperEntry(
        slug="pantau",
        name="Pantau.com",
        module="pantau",
        class_name="PantauScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint + Next.js __NEXT_DATA__ parsing; 2026-05-13",
        supports_latest=True,
    ),
    "voi": ScraperEntry(
        slug="voi",
        name="VOI.id",
        module="voi",
        class_name="VOIScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /en/artikel/cari?q= endpoint + HTML parsing; 2026-05-13",
        supports_latest=True,
    ),
    "voaindonesia": ScraperEntry(
        slug="voaindonesia",
        name="VOA Indonesia",
        module="voaindonesia",
        class_name="VOAIndonesiaScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /s?k= endpoint + HTML parsing; 2026-05-15",
        supports_latest=True,
    ),
    "galamedia": ScraperEntry(
        slug="galamedia",
        name="Galamedia",
        module="galamedia",
        class_name="GalamediaScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint + div.latest__item + keyword-in-title filtering; 2026-04-24",
        supports_latest=True,
    ),
    "jpnn": ScraperEntry(
        slug="jpnn",
        name="JPNN (Jawa Pos News Network)",
        module="jpnn",
        class_name="JpnnScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} + meta[name=jpnncom_news_pubdate] date extraction; 2026-04-24",
        supports_latest=True,
    ),
    "surabayapagi": ScraperEntry(
        slug="surabayapagi",
        name="Surabaya Pagi",
        module="surabayapagi",
        class_name="SurabayaPagiScraper",
        concurrency=3,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /tag/{keyword} + article:published_time; concurrency=3 for rate limiting; 2026-04-24",
        supports_latest=True,
    ),
    "rri": ScraperEntry(
        slug="rri",
        name="RRI (RRI.co.id)",
        module="rri",
        class_name="RRIScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="promoted to stable; /search?q= endpoint with plain HTTP; 2026-04-18",
        supports_latest=True,
    ),
    # ── New batch: 2026-05-batch2 ────────────────────────────────────────────
    "balipost": ScraperEntry(
        slug="balipost",
        name="Bali Post",
        module="balipost",
        class_name="BaliPostScraper",
        concurrency=5,
        status="stable",
        strict_search=False,
        smoke_keyword="ekonomi",
        note="new; latest-only via homepage; WordPress /search?q= returns empty cached page; 2026-05-15",
        supports_search=False,
        supports_latest=True,
    ),
    "dailysocial": ScraperEntry(
        slug="dailysocial",
        name="DailySocial",
        module="dailysocial",
        class_name="DailySocialScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; WordPress /?s= search + wp-block-post containers; 2026-05-15",
        supports_latest=True,
    ),
    "gatra": ScraperEntry(
        slug="gatra",
        name="Gatra",
        module="gatra",
        class_name="GatraScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; WordPress /?s= search + title keyword filtering (search returns all); 2026-05-15",
        supports_latest=True,
    ),
    "kaltimpost": ScraperEntry(
        slug="kaltimpost",
        name="Kaltim Post (Borneo24)",
        module="kaltimpost",
        class_name="KaltimPostScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; WordPress /?s= search + path-based article filtering; 2026-05-15",
        supports_latest=True,
    ),
    "projectmultatuli": ScraperEntry(
        slug="projectmultatuli",
        name="Project Multatuli",
        module="projectmultatuli",
        class_name="ProjectMultatuliScraper",
        concurrency=5,
        status="stable",
        strict_search=True,
        smoke_keyword="ekonomi",
        note="new; Elementor /en/search/{keyword} + e-loop-item containers; 2026-05-15",
        supports_latest=True,
    ),
}


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
            module = importlib.import_module(f".scrapers.{entry.module}", package="newswatch")
            scraper_class = getattr(module, entry.class_name)
            scraper_classes[slug] = {
                "class": scraper_class,
                "params": {"concurrency": entry.concurrency} if entry.concurrency else {},
            }
        except (ImportError, AttributeError) as e:
            logging.warning(f"Failed to load scraper '{slug}': {e}")

    return scraper_classes, linux_excluded
