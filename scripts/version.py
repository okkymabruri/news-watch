#!/usr/bin/env python3
"""Prepare and publish news-watch releases."""

import os
import re
import subprocess
import sys
from pathlib import Path

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def validate_version(version):
    """Require an exact semantic x.y.z version."""
    if not VERSION_PATTERN.fullmatch(version):
        sys.exit(f"Error: invalid version {version!r}; expected x.y.z")
    return version


def get_current_version():
    """Read version from pyproject.toml."""
    pyproject = Path("pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if not match:
        sys.exit("Error: version not found in pyproject.toml")
    return match.group(1)




def bump_version(version, part):
    """Return the requested semantic-version bump."""
    validate_version(version)
    major, minor, patch = map(int, version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _replace_marker(path, pattern, replacement):
    content = path.read_text()
    updated, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
    if count != 1:
        sys.exit(f"Error: expected one version marker in {path}, found {count}")
    return updated


def update_version_files(new_version):
    """Update every source version marker."""
    validate_version(new_version)
    updates = {
        Path("pyproject.toml"): _replace_marker(
            Path("pyproject.toml"),
            r'^version\s*=\s*"[^"]+"',
            f'version = "{new_version}"',
        ),
        Path("src/newswatch/__init__.py"): _replace_marker(
            Path("src/newswatch/__init__.py"),
            r'^__version__\s*=\s*"[^"]+"',
            f'__version__ = "{new_version}"',
        ),
        Path("CITATION.cff"): _replace_marker(
            Path("CITATION.cff"),
            r"^version:\s*.+$",
            f"version: {new_version}",
        ),
    }

    for path, content in updates.items():
        path.write_text(content)
        print(f"Updated {path} to v{new_version}")


def _read_marker(path, pattern, description):
    content = path.read_text()
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        sys.exit(f"Error: {description} version not found in {path}")
    return match.group(1).strip()


def _read_lock_version():
    content = Path("uv.lock").read_text()
    packages = re.finditer(
        r'^\[\[package\]\]\s*$\n(?P<body>.*?)(?=^\[\[package\]\]\s*$|\Z)',
        content,
        re.MULTILINE | re.DOTALL,
    )
    for package in packages:
        body = package.group("body")
        if re.search(r'^name\s*=\s*"news-watch"\s*$', body, re.MULTILINE):
            match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', body, re.MULTILINE)
            if not match:
                sys.exit("Error: news-watch version not found in uv.lock")
            return match.group(1)
    sys.exit("Error: news-watch package not found in uv.lock")


def verify_version_markers(version):
    """Require all release metadata to match the target version."""
    markers = {
        "pyproject.toml": get_current_version(),
        "src/newswatch/__init__.py": _read_marker(
            Path("src/newswatch/__init__.py"),
            r'^__version__\s*=\s*"([^"]+)"',
            "package",
        ),
        "CITATION.cff": _read_marker(
            Path("CITATION.cff"), r"^version:\s*(.+)$", "citation"
        ),
        "uv.lock": _read_lock_version(),
    }
    for path, actual in markers.items():
        if actual != version:
            sys.exit(
                f"Error: VERSION={version} does not match {path} version={actual}"
            )


def verify_changelog(version):
    """Require release notes for the target version."""
    changelog = Path("docs/changelog.md").read_text()
    if not re.search(rf"^## \[{re.escape(version)}\](?:\s|$)", changelog, re.MULTILINE):
        sys.exit(f"Error: no ## [{version}] section found in docs/changelog.md")


def _run_git(*args, capture_output=False):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_SSH_COMMAND"] = "ssh -oBatchMode=yes"
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=capture_output,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
    )


def _git_output(*args):
    return _run_git(*args, capture_output=True).stdout.strip()


def verify_publish_state(version):
    """Require a clean prepared commit at origin/main."""
    branch = _git_output("branch", "--show-current")
    if branch != "main":
        sys.exit(f"Error: release publication requires main, current branch is {branch}")

    if _git_output("status", "--porcelain"):
        sys.exit("Error: release publication requires a clean worktree")

    _run_git("fetch", "origin", "main")

    head = _git_output("rev-parse", "HEAD")
    upstream = _git_output("rev-parse", "origin/main")
    if head != upstream:
        sys.exit("Error: HEAD does not match origin/main")

    tag = f"v{version}"
    if _git_output("tag", "--list", tag):
        sys.exit(f"Error: tag {tag} already exists")

    if _git_output("ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
        sys.exit(f"Error: tag {tag} already exists on origin")


def prepare_release(version):
    """Update release metadata and refresh the lockfile."""
    validate_version(version)
    update_version_files(version)
    subprocess.run(["uv", "lock"], check=True)
    print(f"Prepared version {version}. Review and commit the changes before publishing.")


def publish_release(version):
    """Validate and publish an annotated release tag."""
    validate_version(version)
    verify_version_markers(version)
    verify_changelog(version)
    verify_publish_state(version)

    tag = f"v{version}"
    _run_git("tag", "-a", tag, "-m", f"Release {tag}")
    _run_git("push", "origin", tag)
    print(f"Published tag {tag}")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in {"prepare", "publish"}:
        sys.exit(
            "Usage: python scripts/version.py prepare {VERSION|--patch|--minor|--major}\n"
            "       python scripts/version.py publish VERSION"
        )

    command, value = sys.argv[1:]
    if command == "prepare":
        if value in {"--patch", "--minor", "--major"}:
            value = bump_version(get_current_version(), value[2:])
        prepare_release(value)
    else:
        publish_release(value)


if __name__ == "__main__":
    main()
