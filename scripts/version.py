#!/usr/bin/env python3
"""Simple version management for news-watch."""

import re
import subprocess
import sys
from pathlib import Path


def get_current_version():
    """Read version from pyproject.toml."""
    pyproject = Path("pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if not match:
        sys.exit("Error: version not found in pyproject.toml")
    return match.group(1)


def bump_version(version, part):
    """Bump version number."""
    major, minor, patch = map(int, version.split("."))

    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"  # patch


def update_version_files(new_version):
    """Update version in pyproject.toml and src/newswatch/__init__.py."""
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text()
    new_content = re.sub(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
        content,
        flags=re.MULTILINE,
    )
    pyproject_path.write_text(new_content)
    print(f"Updated pyproject.toml to v{new_version}")

    init_path = Path("src/newswatch/__init__.py")
    init_content = init_path.read_text()
    new_init_content = re.sub(
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{new_version}"',
        init_content,
    )
    init_path.write_text(new_init_content)
    print(f"Updated src/newswatch/__init__.py to v{new_version}")


def git_commit_and_tag(version):
    """Commit version change, create tag, and push."""
    tag = f"v{version}"

    result = subprocess.run(["git", "tag", "-l", tag], capture_output=True, text=True)
    if result.stdout.strip():
        print(f"Tag {tag} already exists")
        return

    subprocess.run(
        ["git", "add", "pyproject.toml", "src/newswatch/__init__.py"], check=True
    )
    subprocess.run(["git", "commit", "-m", f"Bump version to {version}"], check=True)
    print("Committed version changes")

    subprocess.run(["git", "tag", tag], check=True)
    print(f"Created tag {tag}")

    response = input(f"Push commit and tag {tag} to remote? (y/n): ")
    if response.lower() == "y":
        subprocess.run(["git", "push"], check=True)
        subprocess.run(["git", "push", "origin", tag], check=True)
        print(f"Pushed commit and tag {tag}")


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/version.py release [--major|--minor|VERSION]")

    if sys.argv[1] != "release":
        sys.exit("Only 'release' command supported")

    current = get_current_version()
    print(f"Current version: {current}")

    if len(sys.argv) == 2:
        new_version = bump_version(current, "patch")
    elif sys.argv[2] == "--major":
        new_version = bump_version(current, "major")
    elif sys.argv[2] == "--minor":
        new_version = bump_version(current, "minor")
    else:
        new_version = sys.argv[2]

    print(f"New version: {new_version}")
    response = input("Continue? (y/n): ")
    if response.lower() != "y":
        print("Cancelled")
        return

    update_version_files(new_version)
    git_commit_and_tag(new_version)
    print(f"\nDone! Version {new_version} released.")
    print("GitHub Actions will publish to PyPI automatically.")


if __name__ == "__main__":
    main()
