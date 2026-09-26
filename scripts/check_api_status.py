"""Bounded, checkpointed API status campaign. No network work occurs on import."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from newswatch.registry import SCRAPERS

DOCS_PATH = Path(__file__).resolve().parents[1] / "docs/api-status.md"
LABELS = {
    "ok": "✅ Passed", "partial_timeout": "⚠️ Partial timeout",
    "partial_error": "⚠️ Partial error", "no_results": "🔎 Empty",
    "timeout": "⏱️ Timeout", "error": "❌ Error",
    "unsupported": "➖ Unsupported", "excluded": "⏸️ Excluded",
    "not_checked": "❔ Not checked",
}
TERMINAL = set(LABELS) - {"not_checked"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def validate_report(report, args):
    """Reject incomplete or inconsistent snapshots before publication."""
    if (report.get("schema_version") != 1 or report.get("complete") is not True
            or not report.get("completed_at") or not report.get("started_at")
            or report.get("config") != {
                "scrapers": args.selected, "method": args.method,
                "timeout": args.timeout, "budget": args.budget,
            }):
        raise ValueError("invalid or incomplete campaign")
    registry = report.get("registry")
    if registry != [asdict(SCRAPERS[slug]) for slug in sorted(SCRAPERS)]:
        raise ValueError("registry identity changed")
    methods = ("search", "latest") if args.method == "both" else (args.method,)
    expected = {(slug, method) for slug in args.selected for method in methods}
    pairs = report.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != len(expected):
        raise ValueError("missing or duplicate pairs")
    seen = set()
    for pair in pairs:
        key = (pair.get("slug"), pair.get("method"))
        if key not in expected or key in seen:
            raise ValueError("unexpected or duplicate pair")
        seen.add(key)
        entry = SCRAPERS[key[0]]
        excluded = entry.status != "stable"
        unsupported = not getattr(entry, f"supports_{key[1]}")
        status = pair.get("status")
        if excluded or unsupported:
            if status != ("excluded" if excluded else "unsupported") or pair.get("reason") != status:
                raise ValueError("invalid skipped pair")
        elif (status not in TERMINAL - {"excluded", "unsupported"}
              or pair.get("reason") is not None
              or not isinstance(pair.get("checked_at"), str)
              or not pair["checked_at"]
              or (pair.get("article_count") is not None
                  and (type(pair["article_count"]) is not int or pair["article_count"] < 0))
              or (status == "timeout" and pair.get("article_count") not in (None, 0))
              or (status != "timeout" and type(pair.get("article_count")) is not int)
              or (status in {"ok", "partial_error", "partial_timeout"}
                  and not pair.get("article_count"))
              or (status in {"no_results", "error"} and pair.get("article_count") != 0)):
            raise ValueError("invalid checked pair")


def render_markdown(report):
    """Display only vetted registry identity, statuses and timestamps."""
    pairs = {(p["slug"], p["method"]): p for p in report["pairs"]}
    def escape(value):
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    lines = ["# Source Status", "",
             f"Last checked: **{escape(report['completed_at'])}**. Smoke-test snapshot, not a live guarantee.",
             "", "✅ Passed · ⚠️ Partial timeout/error · 🔎 Empty · ⏱️ Timeout · ⏱️ Probe limit (count unknown) · ❌ Error · ➖ Unsupported · ⏸️ Excluded · ❔ Not checked.",
             "", "| Source | Search | Latest | Checked at |", "|---|---|---|---|"]
    for entry in report["registry"]:
        slug = entry["slug"]
        cells = []
        times = {}
        for method in ("search", "latest"):
            pair = pairs.get((slug, method))
            status = (pair or {}).get("status")
            if status is None:
                status = ("excluded" if entry["status"] != "stable" else
                          "unsupported" if not entry[f"supports_{method}"] else "not_checked")
            cells.append(
                "⏱️ Probe limit (count unknown)"
                if status == "timeout" and pair and pair.get("error_type") == "HardTimeout"
                else LABELS[status]
            )
            if pair and pair.get("checked_at"):
                times[method] = pair["checked_at"]
        if len(set(times.values())) > 1:
            checked = " / ".join(f"{method[0].upper()}:{escape(times[method])}"
                                   for method in ("search", "latest") if method in times)
        else:
            checked = escape(next(iter(times.values()))) if times else "—"
        lines.append(f"| {escape(entry['name'])} | {cells[0]} | {cells[1]} | {checked} |")
    return "\n".join(lines) + "\n"


def publish(report, args, original_digest):
    validate_report(report, args)
    if digest(DOCS_PATH) != original_digest:
        raise ValueError("documentation changed during campaign")
    text = render_markdown(report)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=DOCS_PATH.parent,
                                     prefix=".api-status-", delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        if digest(DOCS_PATH) != original_digest:
            raise ValueError("documentation changed during campaign")
        os.replace(temp, DOCS_PATH)
    finally:
        temp.unlink(missing_ok=True)

CHILD = """import json, sys
from newswatch.health import health_report
result = health_report(method=sys.argv[1], scrapers=sys.argv[2],
                       scraper_timeout=int(sys.argv[3]), max_pages=1, limit=1)
print(json.dumps(result))
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def positive(value):
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("must be a positive integer")


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrapers", required=True, help="comma-separated slugs or all")
    parser.add_argument("--method", choices=("search", "latest", "both"), default="both")
    parser.add_argument("--timeout", type=positive, default=60)
    parser.add_argument("--budget", type=positive, default=600)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--markdown", action="store_true", help="publish complete campaign to docs")
    args = parser.parse_args(argv)
    if args.scrapers == "all":
        selected = sorted(SCRAPERS)
    else:
        selected = [slug.strip() for slug in args.scrapers.split(",")]
        if not selected or any(slug not in SCRAPERS for slug in selected):
            parser.error("unknown or empty scraper slug")
        if len(selected) != len(set(selected)):
            parser.error("duplicate scraper slug")
    if args.markdown and (args.scrapers != "all" or args.method != "both"):
        parser.error("--markdown requires --scrapers all --method both")
    if args.output_dir.exists():
        parser.error("output directory must be fresh")
    if not args.output_dir.parent.is_dir():
        parser.error("output directory parent does not exist")
    args.selected = selected
    return args


def checkpoint(path, report):
    """Replace a complete JSON document without exposing a partial write."""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".checkpoint-", delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def live_group_members(pgid):
    """Inspect live members, ignoring zombies awaiting reaping by their parent/init."""
    listing = subprocess.run(["ps", "-axo", "pid=,pgid=,stat="], capture_output=True,
                             text=True, check=True, timeout=2)
    members = []
    for line in listing.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1] == str(pgid) and "Z" not in fields[2]:
            members.append(int(fields[0]))
    return members


def cleanup(proc, deadline):
    """Kill the entire session even if its leader already exited."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=max(0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("child could not be reaped") from exc
    while time.monotonic() < deadline:
        try:
            if not live_group_members(proc.pid):
                return
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise RuntimeError("cannot verify process group cleanup") from exc
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    try:
        if not live_group_members(proc.pid):
            return
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError("cannot verify process group cleanup") from exc
    raise RuntimeError("live descendants survived cleanup")


def probe(slug, method, timeout, deadline):
    """Return sanitized observation; never expose child output or exceptions."""
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout, \
         tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr:
        proc = subprocess.Popen(
            [sys.executable, "-c", CHILD, method, slug, str(timeout)],
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            start_new_session=True, close_fds=True,
        )
        timed_out = False
        cleanup_error = None
        try:
            proc.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                cleanup(proc, min(deadline + 10, time.monotonic() + 10))
            except RuntimeError as exc:
                cleanup_error = str(exc)
        if cleanup_error:
            raise RuntimeError(cleanup_error)
        if timed_out:
            return {"status": "timeout", "article_count": None, "error_type": "HardTimeout"}
        if proc.returncode != 0:
            return {"status": "infrastructure_error", "article_count": None}
        if stdout.seek(0, os.SEEK_END) > 65536 or stderr.seek(0, os.SEEK_END) > 65536:
            return {"status": "infrastructure_error", "article_count": None}
        stdout.seek(0)
        try:
            data = json.load(stdout)
            if (not isinstance(data, list) or len(data) != 1
                    or not isinstance(data[0], dict)
                    or data[0].get("slug") != slug
                    or data[0].get("method") != method
                    or not valid_observation(data[0])):
                raise ValueError("invalid health record")
        except (ValueError, TypeError, AttributeError):
            return {"status": "infrastructure_error", "article_count": None}
        row = data[0]
        error_type = row.get("error_type")
        if not isinstance(error_type, str) or not error_type.isidentifier():
            error_type = None
        return {"status": row["status"], "article_count": row["article_count"],
                "error_type": error_type}


def valid_observation(row):
    status = row.get("status")
    count = row.get("article_count")
    if type(count) is not int or count < 0:
        return False
    if status in {"ok", "partial_timeout", "partial_error"}:
        return count > 0
    if status in {"no_results", "timeout", "error"}:
        return count == 0
    return False


def run(args):
    original_digest = digest(DOCS_PATH) if args.markdown else None
    started = time.monotonic()
    deadline = started + args.budget
    args.output_dir.mkdir(parents=False, exist_ok=False)
    path = args.output_dir / "report.json"
    methods = ("search", "latest") if args.method == "both" else (args.method,)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True, timeout=min(5, max(0.01, deadline - time.monotonic()))).stdout.strip()
    report = {"schema_version": 1, "git_head": head, "started_at": utc_now(),
              "completed_at": None, "complete": False,
              "config": {"scrapers": args.selected, "method": args.method,
                         "timeout": args.timeout, "budget": args.budget},
              "registry": [asdict(SCRAPERS[slug]) for slug in sorted(SCRAPERS)],
              "pairs": []}
    for slug in args.selected:
        entry = SCRAPERS[slug]
        for method in methods:
            reason = ("excluded" if entry.status != "stable" else
                      "unsupported" if not getattr(entry, f"supports_{method}") else None)
            report["pairs"].append({"slug": slug, "method": method,
                                    "status": "not_checked" if reason is None else reason,
                                    "reason": reason or "pending"})
    checkpoint(path, report)
    interrupted = False
    failed = False
    try:
        for pair in report["pairs"]:
            if pair["reason"] != "pending":
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 15:
                pair["reason"] = "budget_exhausted"
                checkpoint(path, report)
                continue
            soft = min(args.timeout, max(1, int(remaining - 15)))
            try:
                # Imports, cancellation and JSON output need a grace interval
                # beyond the scraper's own soft timeout. Keep cleanup inside budget.
                observation = probe(pair["slug"], pair["method"], soft,
                                    min(deadline - 10, time.monotonic() + soft + 5))
            except (RuntimeError, OSError, subprocess.SubprocessError):
                pair.update(status="not_checked", reason="infrastructure_error")
                failed = True
                checkpoint(path, report)
                break
            if observation["status"] != "infrastructure_error" and not (
                observation["status"] == "timeout" and observation["article_count"] is None
            ) and not valid_observation(observation):
                observation = {"status": "infrastructure_error", "article_count": None}
            pair.update(observation)
            pair["reason"] = None
            pair["checked_at"] = utc_now()
            checkpoint(path, report)
            if pair["status"] == "infrastructure_error":
                failed = True
                break
            if any(p["reason"] == "pending" for p in report["pairs"]):
                time.sleep(min(2, max(0, deadline - time.monotonic() - 10)))
    except KeyboardInterrupt:
        interrupted = True
    except (OSError, subprocess.SubprocessError):
        failed = True
    finally:
        for pair in report["pairs"]:
            if pair["reason"] == "pending":
                pair["reason"] = "interrupted" if interrupted else (
                    "infrastructure_error" if failed else "budget_exhausted")
        report["complete"] = not (interrupted or failed or any(
            p["status"] == "not_checked" or p["status"] == "infrastructure_error"
            for p in report["pairs"]))
        report["completed_at"] = utc_now()
        checkpoint(path, report)
    if args.markdown and report["complete"]:
        publish(report, args, original_digest)
    return 0 if report["complete"] else 1


def main(argv=None):
    args = arguments(argv)
    try:
        return run(args)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Campaign infrastructure failure: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
