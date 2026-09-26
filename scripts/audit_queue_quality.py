"""Advisory queue-quality audit for three HTTP-only adapters; no network on import.

Run with --live explicitly. Browser/CSE and other adapters are deliberately unbound.
"""
import argparse
import asyncio
import importlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from newswatch.registry import SCRAPERS
from newswatch.timeutils import project_timezone

SOURCES = frozenset({"cnaindonesia", "gnfi", "rmid"})
CAP = 12
DOMAINS = {"cnaindonesia": "cna.id", "gnfi": "goodnewsfromindonesia.id", "rmid": "rm.id"}
PROMO = re.compile(r"\b(?:advertorial|sponsored|promo|diskon|voucher)\b", re.I)
ROOT = Path(__file__).resolve().parents[1] / "tmp"


class Denied(Exception):
    pass


def canonical(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        raise Denied("invalid_url")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", "", ""))


class Guard:
    """Count each aiohttp hop, including redirects and robots, before dispatch."""
    def __init__(self, session, cap=CAP, shared=None):
        self.session = session
        self.original = session._request
        self.count = 0
        self.cap = cap
        self.shared = shared if shared is not None else self
        self.stopped = None
        self.robots = {}
        self.robots_lock = asyncio.Lock()
        self.user_agent = session.headers["User-Agent"]
        self.dispatch_lock = asyncio.Lock()
        self.last_start = None

    def deny(self, reason):
        self.shared.stopped = self.shared.stopped or reason
        raise Denied(self.shared.stopped)

    async def robots_allowed(self, url, user_agent):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        async with self.robots_lock:
            if origin not in self.robots:
                # No redirect: a redirected robots policy is ambiguous and denied.
                async with await self.request("GET", origin + "/robots.txt", robots=True) as response:
                    if response.status != 200:
                        self.deny("robots_unavailable")
                    text = await response.text()
                parser = RobotFileParser()
                parser.parse(text.splitlines())
                self.robots[origin] = parser
        if not self.robots[origin].can_fetch(user_agent, url):
            self.deny("robots_denied")

    async def request(self, method, url, *, robots=False, **kwargs):
        url = str(url)
        headers = kwargs.get("headers") or {}
        user_agent = next((v for k, v in headers.items() if k.lower() == "user-agent"), self.user_agent)
        for _ in range(self.cap + 1):
            if self.shared.stopped:
                raise Denied(self.shared.stopped)
            try:
                canonical(url)
            except Denied as exc:
                self.deny(str(exc))
            if not robots:
                await self.robots_allowed(url, user_agent)
            async with self.shared.dispatch_lock:
                if self.shared.stopped:
                    raise Denied(self.shared.stopped)
                if self.shared.count >= self.cap:
                    self.deny("request_cap")
                if self.shared.last_start is not None:
                    await asyncio.sleep(max(0, 2 - (time.monotonic() - self.shared.last_start)))
                if self.shared.stopped:
                    raise Denied(self.shared.stopped)
                self.shared.count += 1
                if self.shared is not self:
                    self.count += 1
                self.shared.last_start = time.monotonic()
                # ClientSession.get/post supply allow_redirects=True internally.
                # Handle every redirect ourselves so each hop is counted and checked.
                kwargs.pop("allow_redirects", None)
                response = await self.original(method, url, allow_redirects=False, **kwargs)
                if response.status in {401, 403, 429}:
                    response.release()
                    self.deny(f"http_{response.status}")
                if response.status == 200 and not robots:
                    from newswatch.utils import _looks_blocked
                    if _looks_blocked(await response.text()):
                        response.release()
                        self.deny("challenge")
            if response.status not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("Location")
            response.release()
            if robots or not location:
                self.deny("redirect_denied")
            url = urljoin(url, location)
            if response.status == 303 or (response.status in {301, 302} and method.upper() == "POST"):
                method = "GET"
                kwargs.pop("data", None)
        self.deny("request_cap")


class GuardState:
    def __init__(self):
        self.count = 0
        self.last_start = None
        self.stopped = None
        self.dispatch_lock = asyncio.Lock()


async def child(slug, method):
    """Isolate audit transport overrides, including when called in-process by tests."""
    from newswatch import utils
    from newswatch.scrapers.basescraper import BaseScraper
    saved = (utils._rnet_get, utils._playwright_get, utils.config.get_proxy,
             utils.config.get_max_retries, utils.AsyncScraper.__aenter__, utils.AsyncScraper.fetch,
             BaseScraper.process_page)
    try:
        return await _guarded_child(slug, method)
    finally:
        (utils._rnet_get, utils._playwright_get, utils.config.get_proxy,
         utils.config.get_max_retries, utils.AsyncScraper.__aenter__, utils.AsyncScraper.fetch,
         BaseScraper.process_page) = saved


async def _guarded_child(slug, method):
    from newswatch import utils
    entry = SCRAPERS[slug]
    if slug not in SOURCES or entry.browser_required or entry.status != "stable" or not getattr(entry, f"supports_{method}"):
        return {"status": "skipped", "reason": "unbound_transport"}
    # No retries, proxy, rnet or browser fallback. A denial must propagate through
    # scraper.fetch (which normally catches Exception), so inherit BaseException.
    class Stop(BaseException):
        pass

    async def no_fallback(*args, **kwargs):
        raise Stop("fallback_denied")

    utils._rnet_get = no_fallback
    utils._playwright_get = no_fallback
    utils.config.get_proxy = lambda: None
    utils.config.get_max_retries = lambda: 0
    original_enter = utils.AsyncScraper.__aenter__
    guards = []
    shared = GuardState()

    async def enter(self):
        await original_enter(self)
        guard = Guard(self.session, shared=shared)
        guards.append(guard)

        async def bound_request(method, url, **kwargs):
            if kwargs.get("proxy") is not None:
                raise Stop("proxy_denied")
            kwargs.pop("proxy", None)
            try:
                return await guard.request(method, url, **kwargs)
            except Denied as exc:
                raise Stop(str(exc)) from None

        self.session._request = bound_request
        return self

    utils.AsyncScraper.__aenter__ = enter
    original_fetch = utils.AsyncScraper.fetch
    from newswatch.scrapers.basescraper import BaseScraper
    original_process_page = BaseScraper.process_page
    selection = {"candidate_links": 0, "selected_links": 0}

    async def bounded_process_page(self, links, keyword):
        # Audit a deterministic subset through the real article/queue pipeline.
        # Reserve one request for a redirect or another origin's robots policy.
        ordered = sorted(set(links))
        selection["candidate_links"] += len(ordered)
        remaining = max(0, CAP - shared.count - 1)
        chosen = ordered[:remaining]
        selection["selected_links"] += len(chosen)
        return await original_process_page(self, chosen, keyword) if chosen else False

    BaseScraper.process_page = bounded_process_page

    async def observed_fetch(self, *args, **kwargs):
        result = await original_fetch(self, *args, **kwargs)
        if result is None and shared.count and not shared.stopped:
            shared.transport_error = True
            shared.stopped = "transport_error"
        return result

    utils.AsyncScraper.fetch = observed_fetch
    module = importlib.import_module(f"newswatch.scrapers.{entry.module}")
    cls = getattr(module, entry.class_name)
    queue = asyncio.Queue()
    scraper = cls(keywords=entry.smoke_keyword if method == "search" else "latest", queue_=queue)
    scraper.max_pages = 1
    scraper.max_latest_pages = 1
    status = None
    reason = None
    try:
        await scraper.scrape(method=method)
    except Stop as exc:
        status, reason = "denied", str(exc)
    except Exception:
        status, reason = "error", "scraper_error"
    if shared.stopped:
        status, reason = (("error", "transport_error") if shared.stopped == "transport_error"
                          else ("denied", shared.stopped))
    if not status and getattr(shared, "transport_error", False):
        status, reason = "error", "transport_error"
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    unique = set()
    valid = 0
    relevant = 0
    diagnostics = []
    now = datetime.now(timezone.utc)
    for item in items:
        try:
            link = canonical(item["link"])
            stamp = item["publish_date"]
            host = urlsplit(link).hostname or ""
            title, content = item["title"], item["content"]
            if isinstance(stamp, datetime):
                aware = stamp.replace(tzinfo=project_timezone()) if stamp.tzinfo is None else stamp
                instant = aware.astimezone(timezone.utc)
                dated = datetime(1990, 1, 1, tzinfo=timezone.utc) <= instant <= now + timedelta(days=1)
            else:
                dated = (isinstance(stamp, date) and date(1990, 1, 1) <= stamp
                         <= (now + timedelta(days=1)).astimezone(project_timezone()).date())
            good = (link not in unique and dated and host in {DOMAINS[slug], "www." + DOMAINS[slug]}
                    and isinstance(title, str) and len(title.strip()) >= 12
                    and isinstance(content, str) and len(content.strip()) >= 40
                    and not PROMO.search(title) and not PROMO.search(content[:300]))
            unique.add(link)
            if good:
                valid += 1
                tokens = re.findall(r"\w+", entry.smoke_keyword.casefold())
                visible = re.findall(r"\w+", title.casefold() + " " + urlsplit(link).path.casefold())
                if tokens and all(token in visible for token in tokens):
                    relevant += 1
            if len(diagnostics) < CAP:
                diagnostics.append({"title": re.sub(r"[^\w .,-]", "", str(title))[:70],
                                    "date": str(stamp)[:10], "valid": bool(good)})
        except (KeyError, TypeError, Denied):
            pass
    count = shared.count
    threshold = valid >= 3 and (method != "search" or relevant >= 3)
    return {"status": status or ("pass" if threshold else "fail"),
            "reason": reason, "requests": count, "queued": len(items), "valid_distinct": valid,
            "candidate_links": selection["candidate_links"], "selected_links": selection["selected_links"],
            "title_url_token_matches": relevant if method == "search" else None,
            "diagnostics": diagnostics,
            "topic_semantics": "curated" if slug == "cnaindonesia" and method == "search" else "not_verified"}


def cleanup(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)
    from check_api_status import live_group_members
    if live_group_members(proc.pid):
        raise RuntimeError("descendants_survived")


def probe(slug, method, deadline):
    with tempfile.TemporaryFile(mode="w+t") as output, tempfile.TemporaryFile(mode="w+t") as errors:
        proc = subprocess.Popen([sys.executable, __file__, "--live", "--child", slug, method],
                                stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                start_new_session=True, close_fds=True)
        try:
            proc.wait(timeout=max(0, deadline - time.monotonic()))
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                cleanup(proc)
            except (OSError, RuntimeError, subprocess.TimeoutExpired, subprocess.SubprocessError):
                return {"status": "infrastructure_error", "reason": "cleanup_failed"}
        if timed_out:
            return {"status": "timeout"}
        if proc.returncode or output.seek(0, os.SEEK_END) > 4096:
            return {"status": "infrastructure_error"}
        output.seek(0)
        try:
            row = json.load(output)
            if row.get("status") not in {"pass", "fail", "denied", "skipped", "error"}:
                raise ValueError
            return row
        except (ValueError, TypeError, AttributeError):
            return {"status": "infrastructure_error"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("slugs", nargs="*")
    args = parser.parse_args(argv)
    if args.child:
        if not args.live:
            parser.error("explicit --live required for child")
        if len(args.slugs) != 2 or args.slugs[0] not in SCRAPERS or args.slugs[1] not in {"latest", "search"}:
            return 2
        print(json.dumps(asyncio.run(child(*args.slugs))))
        return 0
    if not args.live:
        parser.error("explicit --live required")
    if not args.slugs or any(slug not in SOURCES and slug != "jakartapost" for slug in args.slugs):
        parser.error("specify only cnaindonesia, gnfi, rmid, or jakartapost (skipped)")
    ROOT.mkdir(exist_ok=True)
    path = ROOT / f"queue-quality-audit-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    deadline = time.monotonic() + 1800
    pairs = [(slug, method) for slug in args.slugs for method in ("search", "latest")]
    report = []
    halted = False
    for slug, method in pairs:
        entry = SCRAPERS[slug]
        if halted:
            result = {"status": "skipped", "reason": "prior_infrastructure_error"}
        elif entry.status != "stable" or not getattr(entry, f"supports_{method}"):
            result = {"status": "skipped", "reason": "ineligible"}
        elif slug not in SOURCES or entry.browser_required:
            result = {"status": "skipped", "reason": "unbound_transport"}
        elif deadline - time.monotonic() <= 70:
            result = {"status": "skipped", "reason": "budget_exhausted"}
        else:
            result = probe(slug, method, min(deadline - 10, time.monotonic() + 60))
            if pairs[-1] != (slug, method):
                time.sleep(min(2, max(0, deadline - time.monotonic() - 70)))
        if result.get("status") == "infrastructure_error":
            halted = True
        report.append({"slug": slug, "method": method,
                       "checked_at": datetime.now(timezone.utc).isoformat(), **result})
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
