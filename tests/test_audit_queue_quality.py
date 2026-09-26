"""Offline safety boundaries for the advisory queue audit."""
import asyncio
from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "audit_queue_quality", Path(__file__).resolve().parents[1] / "scripts/audit_queue_quality.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class Response:
    def __init__(self, status=200, location=None, body="User-agent: *\nAllow: /\n"):
        self.status = status
        self.headers = {"Location": location} if location else {}
        self.body = body

    async def text(self):
        return self.body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def release(self):
        pass


@pytest.mark.asyncio
async def test_concurrent_requests_never_exceed_cap():
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        await asyncio.sleep(0)
        return Response()

    session = Mock(_request=request, headers={"User-Agent": "AuditBot"})
    guard = audit.Guard(session, cap=3)
    results = await asyncio.gather(*(guard.request("GET", "https://example.org/a") for _ in range(8)),
                                   return_exceptions=True)
    assert len(calls) == guard.count == 3
    assert sum(isinstance(result, audit.Denied) for result in results) == 6


@pytest.mark.asyncio
async def test_redirect_counts_each_hop_and_destination_robots():
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        if url.endswith("/a"):
            return Response(302, "https://other.org/b")
        return Response()

    guard = audit.Guard(Mock(_request=request, headers={"User-Agent": "AuditBot"}), cap=4)
    await guard.request("GET", "https://example.org/a")
    assert guard.count == 4
    assert calls == ["https://example.org/robots.txt", "https://example.org/a",
                     "https://other.org/robots.txt", "https://other.org/b"]


@pytest.mark.asyncio
async def test_robots_denial_prevents_article_request():
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        return Response(body="User-agent: *\nDisallow: /private")

    guard = audit.Guard(Mock(_request=request, headers={"User-Agent": "AuditBot"}))
    with pytest.raises(audit.Denied, match="robots_denied"):
        await guard.request("GET", "https://example.org/private")
    assert calls == ["https://example.org/robots.txt"]


def _offline_enter(request):
    async def enter(self):
        self.session = Mock(_request=request, headers={"User-Agent": "AuditBot"})
        return self

    return enter


@pytest.mark.asyncio
async def test_swallowed_article_denial_still_stops_dispatch(monkeypatch):
    from newswatch.registry import SCRAPERS

    entry = SCRAPERS["gnfi"]
    module = __import__(f"newswatch.scrapers.{entry.module}", fromlist=[entry.class_name])
    scraper_cls = getattr(module, entry.class_name)
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        return Response(status=403) if url.endswith("/first") else Response()

    async def fake_scrape(self, method="search"):
        async with self:
            async def get_article(link, keyword):
                try:
                    await self.session._request("GET", link)
                except BaseException:
                    pass

            self.get_article = get_article
            await self.process_page(["https://example.org/first"], "latest")
            try:
                await self.session._request("GET", "https://example.org/next")
            except BaseException:
                pass

    monkeypatch.setattr(scraper_cls, "scrape", fake_scrape)
    monkeypatch.setattr("newswatch.utils.AsyncScraper.__aenter__", _offline_enter(request))
    row = await audit.child("gnfi", "latest")
    assert (row["status"], row["reason"], row["requests"]) == ("denied", "http_403", 2)
    assert calls == ["https://example.org/robots.txt", "https://example.org/first"]


@pytest.mark.asyncio
async def test_three_valid_distinct_items_require_date_title_and_body(monkeypatch):
    from newswatch.registry import SCRAPERS

    entry = SCRAPERS["gnfi"]
    module = __import__(f"newswatch.scrapers.{entry.module}", fromlist=[entry.class_name])
    scraper_cls = getattr(module, entry.class_name)

    async def fake_scrape(self, method="search"):
        for number, stamp, title, content in (
            (1, date.today(), "Indonesian community initiative", "A substantial report about local community projects and their impact."),
            (1, date.today(), "Duplicate article entry", "A substantial report about local community projects and their impact."),
            (2, "2026-01-01", "Invalid publication date", "A substantial report about local community projects and their impact."),
            (3, date.today(), " ", "A substantial report about local community projects and their impact."),
            (4, date.today(), "Missing article content", " "),
            (5, date.today(), "Regional culture continues", "A substantial report about local community projects and their impact."),
            (6, date.today(), "Community programs expand", "A substantial report about local community projects and their impact."),
        ):
            await self.queue_.put({"link": f"https://www.goodnewsfromindonesia.id/{number}",
                                   "publish_date": stamp, "title": title, "content": content})

    monkeypatch.setattr(scraper_cls, "scrape", fake_scrape)
    row = await audit.child("gnfi", "latest")
    assert (row["status"], row["queued"], row["valid_distinct"]) == ("pass", 7, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["future", "offsite", "body", "promo"])
async def test_invalid_items_fail_quality(monkeypatch, case):
    from newswatch.registry import SCRAPERS

    entry = SCRAPERS["gnfi"]
    module = __import__(f"newswatch.scrapers.{entry.module}", fromlist=[entry.class_name])
    scraper_cls = getattr(module, entry.class_name)

    async def fake_scrape(self, method="latest"):
        for number in range(3):
            item = {"link": f"https://goodnewsfromindonesia.id/{number}",
                    "publish_date": date.today(),
                    "title": "Indonesian community project expands",
                    "content": "Community members describe the ongoing work and its regional impact."}
            if number == 2:
                if case == "future":
                    item["publish_date"] = date.today() + timedelta(days=30)
                elif case == "offsite":
                    item["link"] = "https://other.example/article"
                elif case == "body":
                    item["content"] = " "
                else:
                    item["title"] = "Sponsored community project expands"
            await self.queue_.put(item)

    monkeypatch.setattr(scraper_cls, "scrape", fake_scrape)
    row = await audit.child("gnfi", "latest")
    assert (row["status"], row["valid_distinct"]) == ("fail", 2)
    assert len(row["diagnostics"]) == 3


@pytest.mark.asyncio
async def test_search_requires_title_or_url_relevance(monkeypatch):
    from newswatch.registry import SCRAPERS

    entry = SCRAPERS["gnfi"]
    module = __import__(f"newswatch.scrapers.{entry.module}", fromlist=[entry.class_name])
    scraper_cls = getattr(module, entry.class_name)

    async def fake_scrape(self, method="search"):
        for number in range(3):
            await self.queue_.put({"link": f"https://goodnewsfromindonesia.id/article-{number}",
                                   "publish_date": date.today(), "title": "Regional culture continues to grow",
                                   "content": "A detailed report mentioning bali in the article body only."})

    monkeypatch.setattr(scraper_cls, "scrape", fake_scrape)
    row = await audit.child("gnfi", "search")
    assert (row["status"], row["valid_distinct"], row["title_url_token_matches"]) == ("fail", 3, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        (datetime(1990, 1, 1, 0, 0), 0),
        (datetime(1990, 1, 1, 7, 0), 1),
        (datetime(1990, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=7))), 0),
        (datetime(1990, 1, 1, 7, 0, tzinfo=timezone(timedelta(hours=7))), 1),
    ],
)
async def test_datetime_uses_utc_lower_bound_after_timezone_conversion(monkeypatch, stamp, expected):
    from newswatch.registry import SCRAPERS

    entry = SCRAPERS["gnfi"]
    module = __import__(f"newswatch.scrapers.{entry.module}", fromlist=[entry.class_name])
    scraper_cls = getattr(module, entry.class_name)

    async def fake_scrape(self, method="latest"):
        await self.queue_.put({"link": "https://goodnewsfromindonesia.id/article",
                               "publish_date": stamp, "title": "Community project expands",
                               "content": "Community members describe the ongoing work and its regional impact."})

    monkeypatch.setattr(scraper_cls, "scrape", fake_scrape)
    row = await audit.child("gnfi", "latest")
    assert row["valid_distinct"] == expected
    assert row["diagnostics"][0]["valid"] is bool(expected)


def test_cleanup_kills_process_group(monkeypatch):
    # check_api_status is imported by cleanup from the scripts directory in normal execution.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import check_api_status

    monkeypatch.setattr(check_api_status, "live_group_members", lambda pgid: [])
    kill = Mock()
    monkeypatch.setattr(audit.os, "killpg", kill)
    proc = Mock(pid=123)
    audit.cleanup(proc)
    kill.assert_called_once_with(123, audit.signal.SIGKILL)
    proc.wait.assert_called_once_with(timeout=10)


@pytest.mark.asyncio
async def test_fallback_denied_without_launching_browser(monkeypatch):
    from newswatch import utils

    # No network: fake scrape attempts the fallback after the audit installs its guard.
    from newswatch.registry import SCRAPERS
    entry = SCRAPERS["gnfi"]
    module = __import__(f"newswatch.scrapers.{entry.module}", fromlist=[entry.class_name])
    scraper_cls = getattr(module, entry.class_name)

    async def fake_scrape(self, method="search"):
        await utils._playwright_get("https://example.org", None, 1)

    monkeypatch.setattr(scraper_cls, "scrape", fake_scrape)
    try:
        row = await audit.child("gnfi", "latest")
        assert row["status"] == "denied"
        assert row["reason"] == "fallback_denied"
    finally:
        monkeypatch.undo()


def test_child_requires_explicit_live(capsys):
    with pytest.raises(SystemExit) as exc:
        audit.main(["--child", "gnfi", "latest"])
    assert exc.value.code == 2
    assert "explicit --live required for child" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_bounded_article_selection_reserves_request_and_restores_method(monkeypatch):
    from newswatch.scrapers.basescraper import BaseScraper
    from newswatch.registry import SCRAPERS

    original = BaseScraper.process_page
    entry = SCRAPERS["gnfi"]
    module = __import__(f"newswatch.scrapers.{entry.module}", fromlist=[entry.class_name])
    scraper_cls = getattr(module, entry.class_name)
    seen = []

    async def fake_process(self, links, keyword):
        seen.append((list(links), keyword))
        return True

    async def fake_scrape(self, method="search"):
        await self.process_page([f"https://example.org/{i}" for i in range(20)], "bali")

    monkeypatch.setattr(BaseScraper, "process_page", fake_process)
    monkeypatch.setattr(scraper_cls, "scrape", fake_scrape)
    row = await audit.child("gnfi", "search")
    assert row["candidate_links"] == 20
    assert row["selected_links"] == 11
    assert len(seen[0][0]) == 11
    assert BaseScraper.process_page is fake_process
    assert original is not fake_process


def test_whitelist_and_default_closed():
    assert audit.SOURCES == {"cnaindonesia", "gnfi", "rmid"}
    with pytest.raises(SystemExit):
        audit.main(["--live"])


def test_cleanup_failure_stops_later_probes(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    proc = Mock(pid=123, returncode=0)
    proc.wait.return_value = 0
    popen = Mock(return_value=proc)
    monkeypatch.setattr(audit.subprocess, "Popen", popen)
    monkeypatch.setattr(audit, "cleanup", Mock(side_effect=RuntimeError("descendants_survived")))
    monkeypatch.setattr(audit.time, "sleep", Mock())

    assert audit.main(["--live", "gnfi"]) == 0
    reports = list(tmp_path.glob("queue-quality-audit-*.json"))
    assert len(reports) == 1
    rows = audit.json.loads(reports[0].read_text())
    assert rows[0]["status"] == "infrastructure_error"
    assert rows[0]["reason"] == "cleanup_failed"
    assert popen.call_count == 1
    assert rows[1]["status"] == "skipped"


@pytest.mark.asyncio
async def test_effective_request_user_agent_controls_robots():
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        return Response(body="User-agent: GNFI-Agent\nDisallow: /private\nUser-agent: *\nAllow: /")

    guard = audit.Guard(Mock(_request=request, headers={"User-Agent": "Session-Agent"}))
    with pytest.raises(audit.Denied, match="robots_denied"):
        await guard.request("GET", "https://example.org/private", headers={"User-Agent": "GNFI-Agent"})
    assert calls == ["https://example.org/robots.txt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [True, False])
async def test_aiohttp_redirect_default_is_overridden_and_counted(override):
    calls = []

    async def request(method, url, **kwargs):
        calls.append(url)
        return Response()

    guard = audit.Guard(Mock(_request=request, headers={"User-Agent": "AuditBot"}))
    await guard.request("GET", "https://example.org/article", allow_redirects=override)
    assert calls == ["https://example.org/robots.txt", "https://example.org/article"]


@pytest.mark.asyncio
async def test_shared_cap_and_gap_across_sessions(monkeypatch):
    clock = [0.0]
    starts = []

    async def sleep(seconds):
        clock[0] += seconds

    async def request(method, url, **kwargs):
        starts.append((url, clock[0]))
        return Response()

    monkeypatch.setattr(audit.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(audit.asyncio, "sleep", sleep)
    shared = audit.GuardState()
    first = audit.Guard(Mock(_request=request, headers={"User-Agent": "AuditBot"}), cap=3, shared=shared)
    second = audit.Guard(Mock(_request=request, headers={"User-Agent": "AuditBot"}), cap=3, shared=shared)
    await first.request("GET", "https://example.org/a")
    with pytest.raises(audit.Denied, match="request_cap"):
        await second.request("GET", "https://example.org/b")
    assert shared.count == 3
    assert starts == [("https://example.org/robots.txt", 0.0),
                      ("https://example.org/a", 2.0),
                      ("https://example.org/robots.txt", 4.0)]


@pytest.mark.asyncio
async def test_denial_and_spacing(monkeypatch):
    starts = []
    clock = [0.0]

    async def sleep(seconds):
        clock[0] += seconds

    async def request(method, url, **kwargs):
        starts.append((url, clock[0]))
        return Response(status=403) if url.endswith("/a") else Response()

    monkeypatch.setattr(audit.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(audit.asyncio, "sleep", sleep)
    guard = audit.Guard(Mock(_request=request, headers={"User-Agent": "AuditBot"}))
    with pytest.raises(audit.Denied, match="http_403"):
        await guard.request("GET", "https://example.org/a")
    assert starts == [("https://example.org/robots.txt", 0), ("https://example.org/a", 2)]
