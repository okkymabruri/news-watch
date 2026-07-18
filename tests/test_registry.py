"""Registry integrity tests."""
import pytest

from newswatch.registry import (
    ScraperEntry,
    build_registry,
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