"""
The Conversation Indonesia scraper.

Verified endpoints (2026-07-12):
    search:  https://theconversation.com/id/search
             ?date=all
             &date_from=
             &date_to=
             &language=id
             &page={page}
             &q={quoted_keyword}
             &sort=recency
             (GET is sufficient; no CSRF token required)
    latest:  https://theconversation.com/id
    article: https://theconversation.com/{slug}-{id}

Article extraction (verified 2026-07-12):
- title:    meta[property="og:title"]
- date:     <time datetime="..."> (ISO 8601 UTC)
- author:   a[rel="author"] (often multi-author; we keep primary byline text)
- category: a[href*="/topics/"] joined with comma
- body:     div[itemprop="articleBody"] descendants <p> joined, share/print
            boilerplate dropped by length filter

Site config still favours a real Chrome User-Agent: the public search page
serves results when fetched with a browser User-Agent and the documented
Indonesian Accept-Language header.
"""

import logging
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_BASE_URL = "https://theconversation.com"
_LATEST_URL = f"{_BASE_URL}/id"
_SEARCH_URL = f"{_BASE_URL}/id/search"

# /{slug}-{id}; same-site only; topics/authors/partners excluded.
_ARTICLE_RE = re.compile(
    r"^https?://theconversation\.com/[a-z][a-z0-9-]+-\d+(?:[?#].*)?$",
    re.IGNORECASE,
)

# paths that look like articles but are sections/partners/etc.
_SECTION_PREFIXES = (
    "/id/", "/topics/", "/partners/", "/authors/", "/newsletters/",
    "/about-us", "/become-an-author", "/community-standards",
    "/contact-us", "/pitches", "/styleguide", "/us", "/europe",
    "/uk", "/australia", "/africa", "/france",
)


class ConversationIDScraper(BaseScraper):
    """The Conversation (ID edition) static-HTML scraper with
    /id/search support and homepage latest."""

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
            "Accept-Language": "id,en;q=0.9",
        }

    # --- search mode ---
    async def build_search_url(self, keyword, page):
        if page < 1:
            page = 1
        quoted = quote(keyword, safe="")
        url = (
            f"{_SEARCH_URL}"
            f"?date=all"
            f"&date_from="
            f"&date_to="
            f"&language=id"
            f"&page={page}"
            f"&q={quoted}"
            f"&sort=recency"
        )
        return await self.fetch(url, headers=self.headers, timeout=30)

    def parse_article_links(self, response_text):
        return self._collect_article_links(response_text)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("ConversationID empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            return

        publish_date = self._extract_date(soup)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        content = self._extract_content(soup)
        if not content:
            return

        author = self._extract_author(soup)
        category = self._extract_category(soup)

        await self.queue_.put({
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "theconversation.com",
            "link": link,
        })

    # --- latest mode ---
    async def build_latest_url(self, page):
        if page != 1:
            return None
        return await self.fetch(_LATEST_URL, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        return self._collect_article_links(response_text)

    @staticmethod
    def _collect_article_links(response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE_URL, href)
            # strip query for pattern check; keep canonical form
            bare = full.split("?", 1)[0].split("#", 1)[0]
            if any(bare.endswith(seg) or seg in bare for seg in _SECTION_PREFIXES):
                continue
            if _ARTICLE_RE.match(full):
                links.add(bare)
        return links or None

    # --- extraction helpers ---
    @staticmethod
    def _extract_title(soup):
        el = soup.select_one('meta[property="og:title"]')
        if el and el.get("content"):
            return el["content"].strip()
        h1 = soup.select_one("h1")
        return h1.get_text(strip=True) if h1 else ""

    @staticmethod
    def _extract_date(soup):
        time_el = soup.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            return _parse_iso(time_el["datetime"])
        # fallback: meta article:published_time
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            return _parse_iso(meta["content"])
        return None

    @staticmethod
    def _extract_author(soup):
        names = []
        seen = set()
        for sel in ('a[rel="author"]', ".author-name"):
            for a in soup.select(sel):
                txt = a.get_text(strip=True)
                if txt and txt not in seen:
                    seen.add(txt)
                    names.append(txt)
        if names:
            return ", ".join(names)
        meta = soup.select_one('meta[name="author"]')
        if meta and meta.get("content"):
            return meta["content"].strip()
        return "Unknown"

    @staticmethod
    def _extract_category(soup):
        topics = [a.get_text(strip=True) for a in soup.select('a[href*="/topics/"]')
                  if a.get_text(strip=True)]
        if topics:
            seen = []
            for t in topics:
                if t not in seen:
                    seen.append(t)
            return ", ".join(seen[:6])
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        for tag in soup(["script", "style", "noscript", "iframe", "aside"]):
            tag.decompose()
        body = soup.select_one('div[itemprop="articleBody"]') or soup.select_one(
            "div.content-body"
        ) or soup.select_one("article")
        if not body:
            return ""
        paragraphs = []
        for p in body.select("p"):
            txt = p.get_text(" ", strip=True)
            if not txt:
                continue
            # skip share/print/cta stubs
            if txt.lower().startswith(("share ", "print ", "listen to this article")):
                continue
            if len(txt) < 25:
                continue
            paragraphs.append(txt)
        return re.sub(r"\s+", " ", " ".join(paragraphs)).strip()


def _parse_iso(value):
    """Parse ISO 8601 and normalize to naive UTC."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError):
        return None
