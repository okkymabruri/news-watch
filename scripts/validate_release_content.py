#!/usr/bin/env python3
"""Validate user-visible release content before publication."""

from __future__ import annotations

import argparse
import ast
import re
import struct
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\b(?:placeholder|todo|tbd)\b", re.IGNORECASE)
FENCE_RE = re.compile(r"^```([^`]*)$", re.MULTILINE)


def _fenced_blocks(text: str) -> tuple[list[tuple[str, str]], bool]:
    blocks: list[tuple[str, str]] = []
    language: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("```"):
            if language is None:
                language = line[3:].strip().lower()
                lines = []
            else:
                blocks.append((language, "\n".join(lines)))
                language = None
            continue
        if language is not None:
            lines.append(line)
    return blocks, language is None


def validate_readme(path: Path) -> list[str]:
    """Return release-blocking README errors."""
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if PLACEHOLDER_RE.search(text):
        errors.append("README contains a temporary placeholder marker")
    required = (
        "news-watch is a Python package",
        "## Installation",
        "## Usage",
        "## Supported Websites",
    )
    for marker in required:
        if marker not in text:
            errors.append(f"README is missing required content: {marker}")

    blocks, balanced = _fenced_blocks(text)
    if not balanced:
        errors.append("README contains unbalanced Markdown code fences")
        return errors

    bash_blocks = [body for language, body in blocks if language in {"bash", "sh", "shell"}]
    installation = next((body for body in bash_blocks if "pip install news-watch" in body), "")
    if "playwright install chromium" not in installation:
        errors.append("README installation commands must share a balanced shell fence")

    for language, body in blocks:
        if language not in {"python", "py"}:
            continue
        try:
            ast.parse(body)
        except SyntaxError as exc:
            errors.append(f"README Python example is invalid: line {exc.lineno}: {exc.msg}")
    return errors


def validate_png_opacity(path: Path) -> list[str]:
    """Return an error when a published PNG contains transparency."""
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            return [f"{path} is not a valid PNG"]
        length_bytes = stream.read(4)
        chunk_type = stream.read(4)
        if len(length_bytes) != 4 or chunk_type != b"IHDR":
            return [f"{path} has no valid PNG IHDR"]
        length = struct.unpack(">I", length_bytes)[0]
        ihdr = stream.read(length)
        if len(ihdr) != 13:
            return [f"{path} has an invalid PNG IHDR"]
        color_type = ihdr[9]
        if color_type in {4, 6}:
            return [f"{path} contains an alpha channel"]
        stream.read(4)
        while True:
            length_bytes = stream.read(4)
            if not length_bytes:
                break
            if len(length_bytes) != 4:
                return [f"{path} has a truncated PNG chunk"]
            length = struct.unpack(">I", length_bytes)[0]
            chunk_type = stream.read(4)
            if chunk_type == b"tRNS":
                return [f"{path} contains PNG transparency"]
            stream.seek(length + 4, 1)
            if chunk_type == b"IEND":
                break
    return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument(
        "--person-network",
        type=Path,
        default=Path("docs/assets/mbg/person_comention_network.png"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_readme(args.readme)
    errors.extend(validate_png_opacity(args.person_network))
    if errors:
        for error in errors:
            print(f"Error: {error}")
        return 1
    print("Release content validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
