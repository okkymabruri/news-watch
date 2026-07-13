"""
Betahita (betahita.id) scraper.

Verified endpoints (2026-07-12):
    search:  https://www.betahita.id/search?query={quoted_keyword}&pagenum={page}
    latest:  https://www.betahita.id/
    article: https://www.betahita.id/berita/{id}/{slug}
             https://www.betahita.id/opini/{id}/{slug}
             https://www.betahita.id/sorot/{id}/{slug}


Article extraction sources (verified 2026-07-12):
- title:    h1 inside div.judul-artikel
- category: <h5>Berita</h5> / <h5>Opini</h5> inside div.judul-artikel
            (also reachable from the first path segment)
- date:     <h5 class="margin-bottom-sm"> inside div.judul-artikel
            (Indonesian locale: "Sabtu, 11 Juli 2026")
- author:   <h5 class="title"><a>Oleh: ...</a></h5> inside div.box-sumber
- dateline: first <p> inside div.detail-in whose stripped text starts with
            "BETAHITA.ID" (the masthead is rendered as a bold grey prefix)
- content:  paragraphs after the dateline inside div.detail-in, skipping
            figure blocks (div.box-foto-artikel) and any comment/related
            sections that follow the article body

Same-site filter accepts only canonical /{berita|opini|sorot}/{numeric-id}/{slug}
article paths from betahita.id. The canonical /search?query=&pagenum= endpoint
is the sole discovery entry point; internal cross-links are collected
alongside native listings by the shared article-link parser.
"""

import logging
import re
from datetime import datetime
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Comment
from dateparser import parse as _dateparser_parse

from .basescraper import BaseScraper


_BASE_URL = "https://www.betahita.id"
_SOURCE_LABEL = "betahita.id"

_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?betahita\.id/(?:berita|opini|sorot)/\d+/[a-z0-9][a-z0-9-]*$",
    re.IGNORECASE,
)

_DATELINE_PREFIX = "BETAHITA.ID"

# Indonesian weekday and month names used to manually parse the date when the
# dateparser locale coverage misses an entry.
_ID_WEEKDAYS = {
    "senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu",
}
_ID_MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5,
    "juni": 6, "juli": 7, "agustus": 8, "september": 9, "oktober": 10,
    "november": 11, "desember": 12,
}


class BetahitaScraper(BaseScraper):
    """Betahita static-HTML scraper with search and homepage latest."""

    BASE_URL = _BASE_URL

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = _BASE_URL
        self.start_date = start_date
        self.continue_scraping = True
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    async def build_search_url(self, keyword, page):
        """Return search results HTML via the canonical /search?query= endpoint.

        Paginates through the single server-rendered endpoint; queries are
        URL-quoted so multi-word keywords survive.
        """
        if page < 1:
            page = 1
        quoted = quote(keyword, safe="")
        target = f"{_BASE_URL}/search?query={quoted}&pagenum={page}"
        return await self.fetch(target, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        """Return the set of canonical same-site article links in the body."""
        return self._collect_article_links(response_text)

    # Latest path: page 1 of homepage only.
    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(self.base_url, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        return self._collect_article_links(response_text)

    def _collect_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(self.base_url, href)
            if _ARTICLE_RE.match(full):
                links.add(full)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("Betahita empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            logging.warning("Betahita missing title: %s", link)
            return

        publish_date = self._extract_date(soup)
        if not publish_date:
            logging.warning("Betahita missing date: %s", link)
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        content = self._extract_content(soup)
        if not content:
            logging.warning("Betahita empty content: %s", link)
            return

        author = self._extract_author(soup)
        category = self._extract_category(soup, link)

        await self.queue_.put({
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": _SOURCE_LABEL,
            "link": link,
        })

    @staticmethod
    def _extract_title(soup):
        header = soup.select_one("article.detail-artikel div.judul-artikel")
        if not header:
            return ""
        h1 = header.select_one("h1")
        return h1.get_text(strip=True) if h1 else ""

    @staticmethod
    def _extract_date(soup):
        header = soup.select_one("article.detail-artikel div.judul-artikel")
        if not header:
            return None
        # The article date sits in the only <h5 class="margin-bottom-sm"> within the header.
        date_el = header.select_one("h5.margin-bottom-sm")
        if not date_el:
            return None
        raw = date_el.get_text(" ", strip=True)
        return BetahitaScraper._parse_indonesian_date(raw)

    @staticmethod
    def _parse_indonesian_date(raw):
        """Parse "Sabtu, 11 Juli 2026" (with optional time suffix) into naive datetime."""
        if not raw:
            return None
        text = raw.strip()

        # Try dateparser first with explicit Indonesian settings.
        parsed = _dateparser_parse(text, languages=["id"], settings={"PREFER_DAY_OF_MONTH": "first"})
        if parsed:
            return parsed.replace(tzinfo=None)

        # Strip the leading weekday ("Sabtu,") if present.
        comma = text.find(",")
        if comma != -1:
            head = text[:comma].strip().lower()
            if head in _ID_WEEKDAYS:
                text = text[comma + 1:].strip()
        # Drop a trailing time component like " 12:34 WIB".
        m = re.search(r"\s+\d{1,2}[:.]\d{2}(?::\d{2})?(?:\s*WIB|\s*WITA|\s*WIT)?\s*$", text)
        if m:
            text = text[: m.start()].strip()
        parts = text.split()
        if len(parts) != 3:
            return None
        try:
            day = int(parts[0])
        except ValueError:
            return None
        month = _ID_MONTHS.get(parts[1].lower().rstrip("."))
        if not month:
            return None
        try:
            year = int(parts[2])
        except ValueError:
            return None
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _extract_author(soup):
        sumber = soup.select_one("article.detail-artikel div.box-sumber h5.title")
        if not sumber:
            return "Unknown"
        text = sumber.get_text(" ", strip=True)
        if not text:
            return "Unknown"
        # Strip the "Oleh: " byline prefix and any whitespace noise.
        cleaned = re.sub(r"^Oleh\s*:\s*", "", text, flags=re.IGNORECASE).strip()
        return cleaned or "Unknown"

    @staticmethod
    def _extract_category(soup, link):
        header = soup.select_one("article.detail-artikel div.judul-artikel")
        if header:
            for h5 in header.find_all("h5"):
                classes = h5.get("class") or []
                # Skip the date line; it carries the margin-bottom-sm class.
                if "margin-bottom-sm" in classes:
                    continue
                label = h5.get_text(strip=True)
                if label:
                    return label
        # Fallback: derive from the URL path segment.
        if link:
            m = re.match(r"^https?://(?:www\.)?betahita\.id/([^/]+)/", link, re.IGNORECASE)
            if m:
                seg = m.group(1).lower()
                if seg in {"berita", "opini"}:
                    return seg.capitalize()
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        detail = soup.select_one("article.detail-artikel div.detail-in")
        if not detail:
            return ""

        # Strip HTML comments (a commented-out RINGKASAN template lives in markup).
        for comment in detail.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        paragraphs = detail.find_all("p")
        if not paragraphs:
            return ""

        started = False
        collected = []
        for p in paragraphs:
            text = p.get_text(" ", strip=True)
            if not text:
                continue
            if not started:
                # Skip leading paragraphs until we hit the BETAHITA.ID dateline.
                if _DATELINE_PREFIX in text:
                    started = True
                continue
            collected.append(text)

        if not collected:
            return ""
        return re.sub(r"\s+", " ", " ".join(collected)).strip()
