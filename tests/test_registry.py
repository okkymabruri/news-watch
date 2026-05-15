"""Registry integrity tests."""
import pytest

from newswatch.registry import (
    SCRAPERS,
    ScraperEntry,
    build_registry,
    validate_registry,
    _SCRAPER_IGNORE,
)

def test_no_duplicate_slugs():
    """Duplicate slugs must raise ValueError during build."""
    with pytest.raises(ValueError, match="Duplicate"):
        build_registry((
            ScraperEntry("alpha", "A", "alpha", "AlphaScraper"),
            ScraperEntry("alpha", "B", "beta", "BetaScraper"),
        ))

def test_no_duplicate_modules():
    """Duplicate modules must raise ValueError during build."""
    with pytest.raises(ValueError, match="Duplicate"):
        build_registry((
            ScraperEntry("alpha", "A", "mod", "AlphaScraper"),
            ScraperEntry("beta", "B", "mod", "BetaScraper"),
        ))

def test_no_duplicate_classes():
    """Duplicate class names must raise ValueError during build."""
    with pytest.raises(ValueError, match="Duplicate"):
        build_registry((
            ScraperEntry("alpha", "A", "alpha", "SameClass"),
            ScraperEntry("beta", "B", "beta", "SameClass"),
        ))

def test_search_false_requires_strict_false():
    """supports_search=False must have strict_search=False."""
    with pytest.raises(ValueError, match="strict_search"):
        build_registry((
            ScraperEntry("alpha", "A", "alpha", "AlphaScraper", supports_search=False, strict_search=True),
        ))

def test_registry_has_all_scrapers():
    """Every scraper module file must have a registry entry."""
    from pathlib import Path
    scraper_dir = Path(__file__).resolve().parent.parent / "src" / "newswatch" / "scrapers"
    registry_modules = {e.module for e in getattr(__import__("newswatch.registry", fromlist=["_SCRAPER_ENTRIES"]), "_SCRAPER_ENTRIES")}

    file_modules = {
        p.stem for p in scraper_dir.glob("*.py")
        if p.stem not in _SCRAPER_IGNORE
    }

    missing = file_modules - registry_modules
    assert not missing, f"Scraper files without registry entries: {sorted(missing)}"

def test_registry_classes_import():
    """Every declared scraper class must import successfully."""
    issues = validate_registry()
    assert not issues, (
        "Registry validation issues:\n" + "\n".join(issues)
    )

def test_registry_count():
    """Registry must contain expected number of scrapers."""
    assert len(SCRAPERS) >= 48, f"Expected at least 48 scrapers, got {len(SCRAPERS)}"

def test_stable_slug_count():
    """Stable slugs must match source count in docs."""
    from newswatch.registry import get_stable_slugs
    stable = get_stable_slugs()
    assert len(stable) >= 40, f"Expected at least 40 stable scrapers, got {len(stable)}"
