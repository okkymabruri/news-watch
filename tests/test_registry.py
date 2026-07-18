"""Registry integrity tests."""
import pytest

from newswatch.registry import (
    SCRAPERS,
    ScraperEntry,
    build_registry,
    get_available_scrapers_from_registry,
    get_latest_scrapers,
    get_search_scrapers,
    validate_registry,
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


def test_validate_registry_clean():
    """validate_registry must report no issues: every scraper file is registered and every class imports."""
    issues = validate_registry()
    assert not issues, "Registry validation issues:\n" + "\n".join(issues)


def test_capability_views_derive_from_stable_registry_entries():
    stable = {slug: entry for slug, entry in SCRAPERS.items() if entry.status == "stable"}

    assert set(get_search_scrapers()) == {
        slug for slug, entry in stable.items() if entry.supports_search
    }
    assert set(get_latest_scrapers()) == {
        slug for slug, entry in stable.items() if entry.supports_latest
    }


@pytest.mark.parametrize("method", ("search", "latest"))
def test_available_scrapers_import_every_capability_entry(method):
    entries = get_search_scrapers() if method == "search" else get_latest_scrapers()
    available = get_available_scrapers_from_registry(method)

    assert set(available) == set(entries)
    for slug, loaded in available.items():
        assert loaded["class"].__name__ == entries[slug].class_name