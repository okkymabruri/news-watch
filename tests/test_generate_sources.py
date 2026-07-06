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
    "total": 7,
    "stable": 5,
    "search": 4,
    "latest": 6,
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
        assert "7 total sources" in out
        assert "4 with keyword search" in out
        assert "all 7 with latest mode" in out
        # notes mention the policy items
        assert "AP News" in out
        assert "Al Jazeera" in out
        assert "Reuters" in out

    def test_render_architecture_state(self, gs):
        out = gs.render_architecture_state(SAMPLE_STATS)
        assert "| stable | 5 |" in out
        assert "| quarantined | 1 |" in out
        assert "| investigating | 1 |" in out
        assert out.startswith("## Current State")

    def test_render_index_summary(self, gs):
        out = gs.render_index_summary(SAMPLE_STATS)
        assert "supports 7 news scrapers" in out
        assert "all 7 with latest mode" in out
        assert out.endswith("\n")

    def test_render_api_notes(self, gs):
        out = gs.render_api_notes(SAMPLE_STATS)
        assert "## Stable API Notes" in out
        assert "All 7 registered scrapers" in out
        assert "4 of them support the `search` method" in out
        assert "all 7 support `latest`" in out

    def test_render_guide_counts(self, gs):
        out = gs.render_guide_counts(SAMPLE_STATS)
        assert "currently exposes 7 supported scrapers" in out
        assert "No investigating or quarantined sources remain" in out


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