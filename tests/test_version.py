"""Tests for explicit release preparation and publication."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "version.py"
SPEC = importlib.util.spec_from_file_location("version_script", SCRIPT)
assert SPEC and SPEC.loader
version_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(version_script)


def _write_release_files(root: Path, version: str = "1.2.3") -> None:
    (root / "src/newswatch").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "news-watch"\nversion = "{version}"\n'
    )
    (root / "src/newswatch/__init__.py").write_text(
        f'__version__ = "{version}"\n'
    )
    (root / "CITATION.cff").write_text(f"cff-version: 1.2.0\nversion: {version}\n")
    (root / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "dependency"\nversion = "9.0.0"\n'
        f'\n[[package]]\nname = "news-watch"\nversion = "{version}"\n'
    )
    (root / "docs/changelog.md").write_text(
        f"# Changelog\n\n## [{version}] - 2026-07-12\n\n- Release.\n"
    )


def _git_runner(outputs, calls):
    def run(command, **kwargs):
        calls.append((command, kwargs))
        key = tuple(command[1:])
        return subprocess.CompletedProcess(command, 0, stdout=outputs.get(key, ""))

    return run


@pytest.mark.parametrize(
    "value",
    ["1.2", "1.2.3.4", "v1.2.3", "1.2.x", "1.2.3-rc1", " 1.2.3"],
)
def test_validate_version_rejects_non_x_y_z(value):
    with pytest.raises(SystemExit, match="expected x.y.z"):
        version_script.validate_version(value)


def test_prepare_updates_metadata_and_only_runs_uv_lock(tmp_path, monkeypatch):
    _write_release_files(tmp_path, "1.2.3")
    monkeypatch.chdir(tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(version_script.subprocess, "run", run)

    version_script.prepare_release("2.0.0")

    assert 'version = "2.0.0"' in (tmp_path / "pyproject.toml").read_text()
    assert '__version__ = "2.0.0"' in (
        tmp_path / "src/newswatch/__init__.py"
    ).read_text()
    assert "version: 2.0.0" in (tmp_path / "CITATION.cff").read_text()
    assert calls == [(["uv", "lock"], {"check": True})]


def test_prepare_rejects_invalid_version_before_files_or_commands(tmp_path, monkeypatch):
    _write_release_files(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = {
        path: (tmp_path / path).read_text()
        for path in ("pyproject.toml", "src/newswatch/__init__.py", "CITATION.cff")
    }
    calls = []
    monkeypatch.setattr(
        version_script.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(SystemExit, match="expected x.y.z"):
        version_script.prepare_release("v2.0.0")

    assert calls == []
    assert all((tmp_path / path).read_text() == content for path, content in before.items())


def test_publish_validates_then_creates_and_pushes_only_tag(tmp_path, monkeypatch):
    _write_release_files(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = []
    outputs = {
        ("branch", "--show-current"): "main\n",
        ("status", "--porcelain"): "",
        ("rev-parse", "HEAD"): "abc123\n",
        ("rev-parse", "origin/main"): "abc123\n",
        ("tag", "--list", "v1.2.3"): "",
        ("ls-remote", "--tags", "origin", "refs/tags/v1.2.3"): "",
    }
    monkeypatch.setattr(version_script.subprocess, "run", _git_runner(outputs, calls))

    version_script.publish_release("1.2.3")

    commands = [call[0] for call in calls]
    assert ["git", "fetch", "origin", "main"] in commands
    assert commands[-2:] == [
        ["git", "tag", "-a", "v1.2.3", "-m", "Release v1.2.3"],
        ["git", "push", "origin", "v1.2.3"],
    ]
    assert all(command[0] == "git" for command in commands)
    for _, kwargs in calls:
        assert kwargs["check"] is True
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert kwargs["env"]["GCM_INTERACTIVE"] == "never"
        assert kwargs["env"]["GIT_SSH_COMMAND"] == "ssh -oBatchMode=yes"


@pytest.mark.parametrize(
    ("outputs", "message"),
    [
        ({("branch", "--show-current"): "feature\n"}, "requires main"),
        (
            {
                ("branch", "--show-current"): "main\n",
                ("status", "--porcelain"): " M pyproject.toml\n",
            },
            "clean worktree",
        ),
        (
            {
                ("branch", "--show-current"): "main\n",
                ("status", "--porcelain"): "",
                ("rev-parse", "HEAD"): "local\n",
                ("rev-parse", "origin/main"): "remote\n",
            },
            "HEAD does not match origin/main",
        ),
        (
            {
                ("branch", "--show-current"): "main\n",
                ("status", "--porcelain"): "",
                ("rev-parse", "HEAD"): "same\n",
                ("rev-parse", "origin/main"): "same\n",
                ("tag", "--list", "v1.2.3"): "v1.2.3\n",
            },
            "already exists",
        ),
        (
            {
                ("branch", "--show-current"): "main\n",
                ("status", "--porcelain"): "",
                ("rev-parse", "HEAD"): "same\n",
                ("rev-parse", "origin/main"): "same\n",
                ("tag", "--list", "v1.2.3"): "",
                ("ls-remote", "--tags", "origin", "refs/tags/v1.2.3"): "remote-tag\n",
            },
            "already exists on origin",
        ),
    ],
)
def test_publish_rejects_unsafe_git_state_without_mutation(
    tmp_path, monkeypatch, outputs, message
):
    _write_release_files(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(version_script.subprocess, "run", _git_runner(outputs, calls))

    with pytest.raises(SystemExit, match=message):
        version_script.publish_release("1.2.3")

    assert not any(call[0][1:3] in (["tag", "-a"], ["push", "origin"]) for call in calls)


@pytest.mark.parametrize(
    ("path", "old", "new", "message"),
    [
        ("pyproject.toml", 'version = "1.2.3"', 'version = "1.2.4"', "pyproject"),
        (
            "src/newswatch/__init__.py",
            '__version__ = "1.2.3"',
            '__version__ = "1.2.4"',
            "__init__",
        ),
        ("CITATION.cff", "version: 1.2.3", "version: 1.2.4", "CITATION"),
        ("uv.lock", 'version = "1.2.3"', 'version = "1.2.4"', "uv.lock"),
        ("docs/changelog.md", "## [1.2.3]", "## [1.2.4]", "changelog"),
    ],
)
def test_publish_rejects_unprepared_metadata_before_git(
    tmp_path, monkeypatch, path, old, new, message
):
    _write_release_files(tmp_path)
    target = tmp_path / path
    target.write_text(target.read_text().replace(old, new))
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(
        version_script.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(SystemExit, match=message):
        version_script.publish_release("1.2.3")

    assert calls == []


@pytest.mark.parametrize(
    ("part", "expected"),
    [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")],
)
def test_bump_version(part, expected):
    assert version_script.bump_version("1.2.3", part) == expected


def test_main_exposes_only_prepare_and_publish(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["version.py", "release", "1.2.3"])

    with pytest.raises(SystemExit, match=r"(?s)prepare .*publish"):
        version_script.main()
