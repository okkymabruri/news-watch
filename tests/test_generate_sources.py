"""Tests for scripts/generate_sources.py.

Exercises the 6 registry-derived renderers, the marker-replacement helper,
and a meta-test that ensures every renderer only references fields that
exist on ``ScraperEntry`` (no .url, .homepage, or http(s) tokens).
"""
from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import Callable, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_sources.py"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "generate_sources_under_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gs():
    return _load_script()


SAMPLE_STATS: Dict[str, int] = {
    "registered_total": 7,
    "registered_search": 5,
    "registered_latest": 7,
    "stable_total": 5,
    "stable_search": 4,
    "stable_latest": 5,
    "quarantined": 1,
    "investigating": 1,
}


# ── TestRenderers ──────────────────────────────────────────────────────────


class TestRenderers:
    def test_render_readme_heading(self, gs):
        out = gs.render_readme_heading(SAMPLE_STATS)
        assert "## Supported Websites (7)" in out
        assert out.endswith("\n")

    def test_render_readme_counts(self, gs):
        out = gs.render_readme_counts(SAMPLE_STATS)
        assert "7 registered sources" in out
        assert "5 with keyword search" in out
        assert "7 with latest mode" in out
        # notes mention the policy items
        assert "AP News" in out
        assert "Al Jazeera" in out
        assert "Reuters" in out

    def test_render_architecture_state(self, gs):
        out = gs.render_architecture_state(SAMPLE_STATS)
        assert "| registered | 7 |" in out
        assert "| stable | 5 |" in out
        assert "| quarantined | 1 |" in out
        assert "| investigating | 1 |" in out
        assert out.startswith("## Current State")

    def test_render_index_summary(self, gs):
        out = gs.render_index_summary(SAMPLE_STATS)
        assert "supports 5 news scrapers" in out
        assert "7 sources are registered in total" in out
        assert out.endswith("\n")

    def test_render_api_notes(self, gs):
        out = gs.render_api_notes(SAMPLE_STATS)
        assert "## Stable API Notes" in out
        assert "All 7 registered scrapers" in out
        assert "5 of them support the `search` method" in out
        assert "all 7 support `latest`" in out

    def test_render_guide_counts(self, gs):
        out = gs.render_guide_counts(SAMPLE_STATS)
        assert "currently exposes 5 supported scrapers" in out
        assert "1 source under investigation" in out
        assert "5 support latest monitoring" in out


# ── TestRenderBlock ────────────────────────────────────────────────────────


class TestRenderBlock:
    def test_replaces_body_when_changed(self, gs):
        text = (
            "preamble\n"
            "<!-- BEGIN GENERATED: demo -->\n"
            "OLD BODY\n"
            "<!-- END GENERATED: demo -->\n"
            "aftermath\n"
        )

        def renderer(stats):
            return "NEW BODY\n"

        out = gs.render_block(text, "demo", renderer)
        assert "NEW BODY" in out
        assert "OLD BODY" not in out
        assert out.startswith("preamble\n")
        assert out.rstrip().endswith("aftermath")

    def test_preserves_surrounding_text(self, gs):
        text = (
            "AAA\n"
            "<!-- BEGIN GENERATED: keep -->\n"
            "old\n"
            "<!-- END GENERATED: keep -->\n"
            "BBB\n"
        )

        def renderer(stats):
            return "fresh"

        out = gs.render_block(text, "keep", renderer)
        idx_a = out.index("AAA")
        idx_b = out.index("BBB")
        idx_fresh = out.index("fresh")
        assert idx_a < idx_fresh < idx_b
        # markers preserved
        assert "<!-- BEGIN GENERATED: keep -->" in out
        assert "<!-- END GENERATED: keep -->" in out

    def test_missing_marker_raises(self, gs):
        text = "no markers here\n"

        def renderer(stats):
            return "x"

        with pytest.raises(KeyError):
            gs.render_block(text, "absent", renderer)

    def test_multiline_body(self, gs):
        text = (
            "<!-- BEGIN GENERATED: multi -->\n"
            "line one\n"
            "line two\n"
            "line three\n"
            "<!-- END GENERATED: multi -->\n"
        )

        def renderer(stats):
            return "first\nsecond\n"

        out = gs.render_block(text, "multi", renderer)
        # the rendered body replaces all three original lines
        assert "first\nsecond\n" in out
        assert "line one" not in out
        assert "line two" not in out
        assert "line three" not in out
        # markers still in place
        assert out.count("<!-- BEGIN GENERATED: multi -->") == 1
        assert out.count("<!-- END GENERATED: multi -->") == 1


# ── Meta-test: renderers must only reference real ScraperEntry fields ─────


RENDERER_NAMES = [
    "render_readme_heading",
    "render_readme_sources",
    "render_readme_counts",
    "render_architecture_state",
    "render_index_summary",
    "render_api_notes",
    "render_guide_counts",
]

# Tokens that are NOT ScraperEntry fields and would leak a schema mistake.
FORBIDDEN_TOKEN_PATTERNS = [
    r"\.url\b",
    r"\.homepage\b",
    r"\.http\b",
    r"https?://",
]

# Fields that DO exist on ScraperEntry (frozen=True dataclass). The renderer
# only ever receives a stats dict, but if it iterates ScraperEntry, these
# are the only valid attribute names.
ALLOWED_FIELDS = {
    "slug",
    "name",
    "module",
    "class_name",
    "concurrency",
    "status",
    "strict_search",
    "browser_required",
    "smoke_keyword",
    "supports_search",
    "supports_latest",
    "note",
}


def test_renderers_only_reference_registry_fields(gs):
    """Every renderer must be free of forbidden tokens that would imply
    a non-existent ScraperEntry field or a hardcoded URL."""
    combined_pattern = re.compile("|".join(FORBIDDEN_TOKEN_PATTERNS))
    for name in RENDERER_NAMES:
        renderer: Callable[[Dict[str, int]], str] = getattr(gs, name)
        src = inspect.getsource(renderer)
        bad = combined_pattern.findall(src)
        assert not bad, (
            f"{name} references forbidden tokens {bad!r}; "
            f"ScraperEntry has no .url/.homepage/.http fields and "
            f"renderers must not hardcode URLs"
        )


# ── Source-URL mapping ─────────────────────────────────────────────────────


class TestReadmeSources:
    """Focused tests for the readme-sources block.

    These guard against the regression where the README silently lost its
    63 linked sources: missing, duplicated, or unlinked entries would
    slip past the simple counts check.
    """

    def test_every_registry_slug_has_a_url(self, gs):
        """The curated mapping must cover every registry slug."""
        registry_slugs = set(gs._load_registry().SCRAPERS.keys())
        mapping = gs.get_source_url_map()
        assert registry_slugs <= mapping.keys()

    def test_no_extra_slugs_in_mapping(self, gs):
        """The curated mapping must not invent slugs the registry doesn't
        have (would render dead links)."""
        registry_slugs = set(gs._load_registry().SCRAPERS.keys())
        mapping = gs.get_source_url_map()
        assert mapping.keys() <= registry_slugs

    def test_mapping_keys_match_registry_exactly(self, gs):
        """Symmetric set-equality: validation must catch drift in either
        direction (new source added or removed from registry)."""
        gs.validate_source_url_map(gs.get_source_url_map())

    def test_mapping_drift_missing_raises(self, gs):
        """Dropping a slug from the mapping must raise (not silently
        disappear from README)."""
        bad = dict(gs.get_source_url_map())
        bad.pop("kompas")
        with pytest.raises(ValueError, match="missing from mapping"):
            gs.validate_source_url_map(bad)

    def test_mapping_drift_extra_raises(self, gs):
        """An extra slug not in the registry must raise (would otherwise
        produce a dead link or duplicate)."""
        bad = dict(gs.get_source_url_map())
        bad["ghost-source"] = "https://example.com"
        with pytest.raises(ValueError, match="not in registry"):
            gs.validate_source_url_map(bad)

    def test_mapping_drift_duplicate_url_raises(self, gs):
        bad = dict(gs.get_source_url_map())
        bad["kompas"] = bad["detik"]
        with pytest.raises(ValueError, match="duplicate URLs"):
            gs.validate_source_url_map(bad)


    def test_render_readme_sources_contains_every_registry_entry(self, gs):
        registry = gs._load_registry().SCRAPERS
        out = gs.render_readme_sources(gs.compute_stats())
        link_lines = [line for line in out.splitlines() if line.startswith("[")]
        assert len(link_lines) == len(registry)

    def test_render_readme_sources_has_no_duplicates(self, gs):
        """Each slug must appear exactly once. A duplicate would imply
        either a mapping key collision or a renderer that lists the
        same entry twice."""
        out = gs.render_readme_sources(gs.compute_stats())
        urls = re.findall(r"\]\((https://[^)]+)\)", out)
        assert len(urls) == len(set(urls))

    def test_render_readme_sources_is_deterministic(self, gs):
        """Two consecutive renders with the same input must produce
        byte-identical output. Catches any state-leak or ordering bug."""
        stats = gs.compute_stats()
        first = gs.render_readme_sources(stats)
        second = gs.render_readme_sources(stats)
        assert first == second

    def test_render_readme_sources_uses_registry_names(self, gs):
        """Display labels must come from the registry (so renaming a
        scraper in code automatically updates the README), not from
        the URL mapping."""
        out = gs.render_readme_sources(gs.compute_stats())
        # Pick a sample of well-known sources; each name should appear.
        assert "[Kompas]" in out
        assert "[Detik]" in out
        assert "[CNN Indonesia]" in out
        # And every link must use https://
        for line in out.splitlines():
            assert line.startswith("["), line
            assert "](" in line, line
            assert "https://" in line, line

    def test_render_readme_sources_block_in_readme(self, gs):
        """The rendered body must match what's actually between the
        readme-sources markers in README.md — prevents the README
        losing the list while the generator still computes it."""
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        stats = gs.compute_stats()
        expected_body = gs.render_readme_sources(stats)
        block_re = re.compile(
            r"<!-- BEGIN GENERATED: readme-sources -->\n(?P<body>.*?)<!-- END GENERATED: readme-sources -->\n?",
            re.DOTALL,
        )
        match = block_re.search(text)
        assert match, "readme-sources marker block missing from README.md"
        assert match.group("body").rstrip("\n") == expected_body.rstrip("\n")

    def test_readme_has_heading_then_sources_then_counts(self, gs):
        """Document order contract: heading block, sources block, counts
        block — in that order, each separated by a blank line."""
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        heading_pos = text.find("<!-- BEGIN GENERATED: readme-heading -->")
        sources_pos = text.find("<!-- BEGIN GENERATED: readme-sources -->")
        counts_pos = text.find("<!-- BEGIN GENERATED: readme-counts -->")
        assert heading_pos != -1
        assert sources_pos != -1
        assert counts_pos != -1
        assert heading_pos < sources_pos < counts_pos