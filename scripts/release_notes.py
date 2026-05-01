#!/usr/bin/env python3
"""Extract release notes from docs/changelog.md."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "docs" / "changelog.md"
PYPROJECT = ROOT / "pyproject.toml"


def current_version() -> str:
    content = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        sys.exit("Error: version not found in pyproject.toml")
    return match.group(1)


def extract_release_notes(version: str) -> str:
    content = CHANGELOG.read_text()
    escaped = re.escape(version)
    pattern = re.compile(
        rf"^## \[{escaped}\].*?\n(?P<body>.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        sys.exit(f"Error: release notes for {version} not found in {CHANGELOG}")

    body = match.group("body").strip()
    if not body:
        sys.exit(f"Error: release notes for {version} are empty")
    return body


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract release notes for a version from docs/changelog.md."
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Version to extract, without the leading v. Defaults to pyproject.toml.",
    )
    args = parser.parse_args()

    version = args.version or current_version()
    print(extract_release_notes(version))


if __name__ == "__main__":
    main()
