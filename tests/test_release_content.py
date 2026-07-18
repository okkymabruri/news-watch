"""Release-content validator tests."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_release_content.py"

if not _SCRIPT.exists():
    pytest.skip(
        f"validator script not implemented yet: {_SCRIPT}",
        allow_module_level=True,
    )

_SPEC = importlib.util.spec_from_file_location("validate_release_content", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    pytest.skip(
        f"validator spec failed to build: {_SCRIPT}",
        allow_module_level=True,
    )

validator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validator)


# ---------------------------------------------------------------------------
# README fixtures
VALID_README = """\
# news-watch

news-watch is a Python package that aggregates headlines from
Indonesian news sources for keyword and date filtered research.

## Installation

```bash
pip install news-watch
playwright install chromium
```

## Usage

```bash
newswatch --help
```

## Supported Websites

See the canonical list below.
"""


def _write_readme(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "README.md"
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# README acceptance -- each test names one observable contract
# ---------------------------------------------------------------------------


def test_validate_readme_accepts_corrected_release_readme(tmp_path):
    """A README with intro + ## Installation + balanced bash fence is clean."""
    path = _write_readme(tmp_path, VALID_README)
    assert validator.validate_readme(path) == []


@pytest.mark.parametrize(
    "marker",
    [
        "## placeholder",
        "## Placeholder",
        "## PLACEHOLDER",
        "## pLaCeHoLdEr",
        "## placeholder notes",
        "## PlaceHolder section",
    ],
)
def test_validate_readme_rejects_placeholder_marker_case_insensitive(
    tmp_path, marker
):
    body = (
        "# news-watch\n\n"
        "news-watch scrapes Indonesian news sources.\n\n"
        f"{marker}\n\n"
        "Some body text.\n\n"
        "## Installation\n\n"
        "```bash\npip install news-watch\n```\n"
    )
    path = _write_readme(tmp_path, body)
    violations = validator.validate_readme(path)
    assert any("placeholder" in v.lower() for v in violations), (
        f"expected a placeholder rejection, got {violations!r}"
    )


def test_validate_readme_rejects_missing_package_introduction(tmp_path):
    # The validator requires the canonical intro substring
    # `news-watch is a Python package`.  Drop only that line.
    body = (
        "# news-watch\n\n"
        "## Installation\n\n"
        "```bash\npip install news-watch\nplaywright install chromium\n```\n\n"
        "## Usage\n\n"
        "```bash\nnewswatch --help\n```\n\n"
        "## Supported Websites\n\n"
        "See the canonical list.\n"
    )
    path = _write_readme(tmp_path, body)
    violations = validator.validate_readme(path)
    assert any(
        re.search(r"is a python package", v, re.IGNORECASE) for v in violations
    ), f"expected missing-introduction rejection, got {violations!r}"


def test_validate_readme_rejects_missing_installation_section(tmp_path):
    body = (
        "# news-watch\n\n"
        "news-watch scrapes Indonesian news sources.\n\n"
        "## Usage\n\n"
        "```bash\nnewswatch --help\n```\n"
    )
    path = _write_readme(tmp_path, body)
    violations = validator.validate_readme(path)
    assert any(
        re.search(r"installation", v, re.IGNORECASE) for v in violations
    ), f"expected missing-installation rejection, got {violations!r}"


def test_validate_readme_rejects_unbalanced_markdown_fences(tmp_path):
    # Three opening fences, two closings -> one unclosed code block.
    body = (
        "# news-watch\n\n"
        "news-watch scrapes Indonesian news sources.\n\n"
        "## Installation\n\n"
        "```bash\n"
        "pip install news-watch\n"
        "```\n\n"
        "```python\n"
        "import newswatch\n"
        "```\n\n"
        "```\n"
        "trailing unclosed fence\n"
    )
    path = _write_readme(tmp_path, body)
    violations = validator.validate_readme(path)
    assert any(
        re.search(r"unbalanced|unclosed|fence", v, re.IGNORECASE)
        for v in violations
    ), f"expected unbalanced-fence rejection, got {violations!r}"


def test_validate_readme_rejects_malformed_python_fence_with_missing_close_paren(tmp_path):
    # Balanced fence; inside the python block a single print() drops its ')'.
    body = (
        "# news-watch\n\n"
        "news-watch scrapes Indonesian news sources.\n\n"
        "## Installation\n\n"
        "```bash\npip install news-watch\n```\n\n"
        "```python\n"
        "import newswatch\n"
        'print("hello"\n'
        "```\n"
    )
    path = _write_readme(tmp_path, body)
    violations = validator.validate_readme(path)
    assert any(
        re.search(r"python|parenthes|paren|missing close", v, re.IGNORECASE)
        for v in violations
    ), (
        "expected rejection for malformed Python fenced code (missing ')'); "
        f"got {violations!r}"
    )


def test_validate_readme_accepts_install_commands_inside_balanced_bash_fence(tmp_path):
    body = (
        "# news-watch\n\n"
        "news-watch is a Python package that aggregates news headlines.\n\n"
        "## Installation\n\n"
        "```bash\npip install news-watch\nplaywright install chromium\n```\n\n"
        "## Usage\n\n"
        "Run `newswatch --help`.\n\n"
        "## Supported Websites\n\n"
        "See the canonical list.\n"
    )
    path = _write_readme(tmp_path, body)
    assert validator.validate_readme(path) == []


def test_validate_readme_rejects_install_commands_outside_balanced_bash_fence(tmp_path):
    # Same commands but rendered as plain paragraphs (no ```bash``` wrapper).
    body = (
        "# news-watch\n\n"
        "news-watch scrapes Indonesian news sources.\n\n"
        "## Installation\n\n"
        "pip install news-watch\n\n"
        "playwright install chromium\n\n"
    )
    path = _write_readme(tmp_path, body)
    violations = validator.validate_readme(path)
    assert violations, (
        "expected violations when install commands appear outside a balanced "
        "bash fence; validator returned an empty list"
    )


# ---------------------------------------------------------------------------
# CLI smoke (defaults + nonzero exit on violation)
# ---------------------------------------------------------------------------


def test_cli_exits_nonzero_on_validation_violation(tmp_path, capsys):
    bad_readme = tmp_path / "README.md"
    bad_readme.write_text(
        "# news-watch\n\n## placeholder\n\nno intro\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--readme",
            str(bad_readme),
        ],
        capture_output=True,
        text=True,
    )
    combined = (result.stdout + result.stderr).lower()
    assert result.returncode != 0, (
        f"validator should exit nonzero on a broken README; got rc={result.returncode}"
    )
    assert combined.strip(), "validator should print actionable diagnostic text"


