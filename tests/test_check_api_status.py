"""Offline campaign isolation and selection checks."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_api_status.py"
spec = importlib.util.spec_from_file_location("check_api_status", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_reject_unknown_and_duplicate_before_output(tmp_path):
    for selection in ("not-a-source", "bbc,bbc", "bbc,"):
        with pytest.raises(SystemExit) as error:
            checker.arguments(["--scrapers", selection, "--output-dir", str(tmp_path / "out")])
        assert error.value.code == 2
        assert not (tmp_path / "out").exists()


def test_markdown_requires_full_source_and_mode_selection(tmp_path):
    for selection, method in (("bbc", "both"), ("all", "search")):
        with pytest.raises(SystemExit) as error:
            checker.arguments([
                "--scrapers", selection, "--method", method,
                "--markdown", "--output-dir", str(tmp_path / "out"),
            ])
        assert error.value.code == 2
        assert not (tmp_path / "out").exists()


def test_no_implicit_sweep(tmp_path):
    args = checker.arguments(["--scrapers", "bbc", "--output-dir", str(tmp_path / "out")])
    assert args.selected == ["bbc"]
    assert args.method == "both"


def test_malformed_child_output_is_infrastructure_error(monkeypatch):
    monkeypatch.setattr(checker, "CHILD", "print('not json')")
    result = checker.probe("bbc", "search", 2, time.monotonic() + 2)
    assert result["status"] == "infrastructure_error"


@pytest.mark.parametrize(
    ("status", "count"),
    [("ok", 0), ("ok", True), ("ok", -1), ("partial_timeout", 0),
     ("no_results", 1), ("skipped", 0)],
)
def test_invalid_health_record_fails_closed(monkeypatch, status, count):
    monkeypatch.setattr(checker, "CHILD", (
        "import json; print(json.dumps([{'slug':'bbc','method':'search',"
        f"'status':{status!r},'article_count':{count!r}}}]))"
    ))
    result = checker.probe("bbc", "search", 2, time.monotonic() + 2)
    assert result == {"status": "infrastructure_error", "article_count": None}


def test_wrong_method_fails_closed(monkeypatch):
    monkeypatch.setattr(checker, "CHILD", (
        "import json; print(json.dumps([{'slug':'bbc','method':'latest',"
        "'status':'ok','article_count':1}]))"
    ))
    assert checker.probe("bbc", "search", 2, time.monotonic() + 2)["status"] == "infrastructure_error"


def test_cooperative_soft_timeout_retains_partial_count(monkeypatch):
    monkeypatch.setattr(checker, "CHILD", """import asyncio, json
from unittest.mock import patch
from newswatch.health import health_report
class S:
    def __init__(self, keywords, queue_, **kwargs):
        self.queue_ = queue_
        self._articles_collected = 0
    async def scrape(self, method):
        await self.queue_.put({'title': 'observed before timeout'})
        self._articles_collected = 1
        await asyncio.sleep(30)
with patch('newswatch.health.get_available_scrapers', return_value={
    'bbc': {'class': S, 'params': {}}
}):
    result = health_report(method='search', scrapers='bbc', scraper_timeout=1, limit=1)
print(json.dumps(result))
""")
    result = checker.probe("bbc", "search", 1, time.monotonic() + 6)
    assert result["status"] == "partial_timeout"
    assert result["article_count"] == 1


def test_hard_timeout_has_unknown_count(monkeypatch):
    monkeypatch.setattr(checker, "CHILD", "import time; time.sleep(30)")
    result = checker.probe("bbc", "search", 1, time.monotonic() + 0.1)
    assert result["status"] == "timeout"
    assert result["article_count"] is None


def test_checkpoint_and_unsupported_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(checker, "probe", lambda *args: {"status": "ok", "article_count": 1})
    monkeypatch.setattr(checker.time, "sleep", lambda _: None)
    directory = tmp_path / "run"
    args = checker.arguments(["--scrapers", "bbc", "--method", "both",
                              "--output-dir", str(directory)])
    assert checker.run(args) == 0
    report = json.loads((directory / "report.json").read_text())
    assert report["complete"]
    assert len(report["registry"]) == len(checker.SCRAPERS)
    assert len(report["pairs"]) == 2


def test_oversized_child_output_is_infrastructure_error(monkeypatch):
    monkeypatch.setattr(checker, "CHILD", "print('secret' * 12000)")
    assert checker.probe("bbc", "search", 2, time.monotonic() + 2) == {
        "status": "infrastructure_error", "article_count": None,
    }


def test_budget_incomplete_without_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(checker, "probe", lambda *args: pytest.fail("unexpected probe"))
    monkeypatch.setattr(checker, "checkpoint", checker.checkpoint)
    args = checker.arguments(["--scrapers", "bbc", "--budget", "1",
                              "--output-dir", str(tmp_path / "run")])
    assert checker.run(args) == 1
    report = json.loads((args.output_dir / "report.json").read_text())
    assert not report["complete"]
    assert all(pair["reason"] == "budget_exhausted" for pair in report["pairs"])


def test_markdown_partial_campaign_and_registry_rows(tmp_path, monkeypatch):
    doc = tmp_path / "api-status.md"
    doc.write_text("original")
    monkeypatch.setattr(checker, "DOCS_PATH", doc)
    monkeypatch.setattr(checker, "probe", lambda *args: {"status": "partial_timeout", "article_count": 1})
    monkeypatch.setattr(checker.time, "sleep", lambda _: None)
    args = checker.arguments(["--scrapers", "bbc", "--method", "search",
                              "--output-dir", str(tmp_path / "run")])
    assert checker.run(args) == 0
    assert doc.read_text() == "original"  # A pilot cannot replace the full snapshot.
    text = checker.render_markdown(json.loads((args.output_dir / "report.json").read_text()))
    assert "⚠️ Partial timeout" in text
    assert "❔ Not checked" in text
    assert len([line for line in text.splitlines() if line.startswith("| ")]) == len(checker.SCRAPERS) + 1
    assert "➖ Unsupported" in text
    assert "⏸️ Excluded" in text


def test_incomplete_does_not_change_document(tmp_path, monkeypatch):
    doc = tmp_path / "api-status.md"
    doc.write_text("original")
    monkeypatch.setattr(checker, "DOCS_PATH", doc)
    monkeypatch.setattr(checker, "probe", lambda *args: pytest.fail("unexpected probe"))
    args = checker.arguments(["--scrapers", "all", "--budget", "1", "--markdown",
                              "--output-dir", str(tmp_path / "run")])
    assert checker.run(args) == 1
    assert doc.read_text() == "original"


def test_publish_guards_and_differing_dates(tmp_path, monkeypatch):
    doc = tmp_path / "api-status.md"
    doc.write_text("original")
    monkeypatch.setattr(checker, "DOCS_PATH", doc)
    args = checker.arguments(["--scrapers", "all", "--markdown",
                              "--output-dir", str(tmp_path / "run")])
    pairs = []
    for slug, entry in sorted(checker.SCRAPERS.items()):
        for mode, date in (("search", "day1"), ("latest", "day2")):
            status = ("excluded" if entry.status != "stable" else
                      "unsupported" if not getattr(entry, f"supports_{mode}") else "ok")
            pairs.append({"slug": slug, "method": mode, "status": status,
                          "reason": status if status in {"excluded", "unsupported"} else None,
                          "checked_at": date if status == "ok" else None,
                          "article_count": 1 if status == "ok" else None})
    report = {"schema_version": 1, "complete": True, "started_at": "start",
              "completed_at": "end", "config": {"scrapers": args.selected,
              "method": "both", "timeout": 60, "budget": 600},
              "registry": [asdict(checker.SCRAPERS[slug]) for slug in sorted(checker.SCRAPERS)],
              "pairs": pairs}
    original = checker.digest(doc)
    checker.publish(report, args, original)
    assert "S:day1 / L:day2" in doc.read_text()
    valid = doc.read_text()
    checker.publish(report, args, checker.digest(doc))
    for mutation in (lambda r: r.update(complete=False),
                     lambda r: r["pairs"].append(dict(r["pairs"][0])),
                     lambda r: r["pairs"][0].pop("checked_at"),
                     lambda r: r["registry"][0].update(name="changed")):
        import copy
        broken = copy.deepcopy(report)
        mutation(broken)
        with pytest.raises(ValueError):
            checker.publish(broken, args, checker.digest(doc))
        assert doc.read_text() == valid
    doc.write_text("concurrent edit")
    with pytest.raises(ValueError, match="changed"):
        checker.publish(report, args, original)
    assert doc.read_text() == "concurrent edit"


def test_render_distinguishes_hard_limit_from_scraper_timeout():
    report = {"completed_at": "today", "registry": [{
        "slug": "bbc", "name": "BBC", "status": "stable",
        "supports_search": True, "supports_latest": True,
    }], "pairs": [{
        "slug": "bbc", "method": "search", "status": "timeout",
        "article_count": None, "error_type": "HardTimeout", "checked_at": "now",
    }, {
        "slug": "bbc", "method": "latest", "status": "timeout",
        "article_count": 0, "error_type": "TimeoutError", "checked_at": "now",
    }]}
    text = checker.render_markdown(report)
    assert "⏱️ Probe limit (count unknown)" in text
    assert "| ⏱️ Probe limit (count unknown) | ⏱️ Timeout |" in text


def test_render_escapes_registry_name():
    report = {"completed_at": "today", "registry": [{"slug": "x", "name": "A|B\\C\nD",
              "status": "stable", "supports_search": True, "supports_latest": True}], "pairs": []}
    assert "A\\|B\\\\C D" in checker.render_markdown(report)
    assert "✅ Passed" in checker.LABELS.values()
    assert "⚠️ Partial error" in checker.LABELS.values()
    assert "🔎 Empty" in checker.LABELS.values()
    assert "⏱️ Timeout" in checker.LABELS.values()
    assert "❌ Error" in checker.LABELS.values()


def test_cleanup_kills_term_ignoring_descendant_after_leader_exit(tmp_path):
    marker = tmp_path / "descendant.pid"
    descendant = (
        "import os,signal,time; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "open(os.environ['PID_MARKER'],'w').write(str(os.getpid())); "
        "time.sleep(30)"
    )
    leader = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}]); "
        "print('done',flush=True)"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", leader],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PID_MARKER": str(marker)},
        start_new_session=True,
    )
    try:
        proc.wait(timeout=3)
        limit = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < limit:
            time.sleep(0.02)
        assert marker.exists()
        pid = int(marker.read_text())
        assert pid in checker.live_group_members(proc.pid)
        checker.cleanup(proc, time.monotonic() + 3)
        assert pid not in checker.live_group_members(proc.pid)
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
