"""
Independen.id scraper — Indonesian investigative journalism outlet (Drupal).

Verified endpoints (2026-07-12):
    latest:  https://independen.id/
    article: https://independen.id/{slug}

Article extraction (verified 2026-07-12):
- title:    meta[property="og:title"] (with "- Independen.id" suffix stripped)
- date:     meta[property="article:published_time"] (ISO 8601)
- author:   meta[name="author"]  (fallback: <span class="field-name-author">)
- category: meta[property="article:section"] (fallback: first breadcrumb link)
- body:     <p> children of <article>; share/related/footer blocks removed.

No keyword search endpoint is exposed; latest-only is implemented via the
homepage. Search/keyword-discoverable routes are rejected as exclusions so
internal chaff is never enqueued:

    node/{id}            -> Drupal canonical node links
    taxonomy/term/{id}   -> category/term pages
    user/{id}            -> author profiles
    user/{name}/...      -> user alias variants
    tags/{name}          -> tag landing pages
    agenda/...           -> event calendar entries
    /category/...        -> legacy category aliases
    /frontpages, /about, /contact, /advertise, /pedoman, /kontak, /privacy,
      /ketentuan, /redaksi, /penulis, /kolom

Latest is latest-only — homepage page 1.
"""

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


_BASE_URL = "https://independen.id"
_SOURCE_LABEL = "independen.id"

# Root-level article slug: lowercase letters/numbers/underscore/dash segments.
_ARTICLE_RE = re.compile(
    r"^https?://independen\.id/[a-z0-9][a-z0-9_-]*(?:/[a-z0-9][a-z0-9_-]*)*/?$",
    re.IGNORECASE,
)

# Anything matching one of these prefixes is treated as a non-article route.
# Drupal idioms (node/, taxonomy/, user/, frontpages) plus the navigation
# targets verified in the homepage markup are excluded up-front so an
# out-of-band link never slips into the queue.
_EXCLUDED_PREFIXES = (
    "/node/",
    "/taxonomy/",
    "/user/",
    "/users/",
    "/tags/",
    "/tag/",
    "/agenda/",
    "/category/",
    "/kategori/",
    "/frontpages",
    "/front-page",
    "/tentang",
    "/about",
    "/contact",
    "/kontak",
    "/pedoman",
    "/ketentuan",
    "/privacy",
    "/advertise",
    "/iklan",
    "/redaksi",
    "/penulis",
    "/kolom",
    "/search",
    "/berita",
    "/politik",
    "/hukum-dan-ham",
    "/ekonomi",
    "/lingkungan",
    "/kesehatan",
    "/teknologi",
    "/pendidikan",
    "/budaya",
    "/opini",
    "/feature",
    "/investigasi",
    "/infografis",
    "/video",
    "/foto",
    "/galeri",
    "/live",
)

# Extensions and asset paths are not articles.
_ASSET_EXT_RE = re.compile(
    r"\.(?:png|jpe?g|gif|webp|svg|pdf|mp4|m4a|mp3|zip|tar(?:\.gz)?)$",
    re.IGNORECASE,
)

# Title suffix observed in og:title.
_TITLE_SUFFIX = "- Independen.id"


def _parse_iso(value):
    """Parse ISO 8601 timestamps into naive UTC datetimes."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class IndependenScraper(BaseScraper):
    """Independen.id static-HTML latest-only scraper.

    Latest: https://independen.id/
    Article: https://independen.id/{slug}
    """

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = _BASE_URL
        self.start_date = start_date
        self.continue_scraping = True
        self.max_latest_pages = 1
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "id,en;q=0.8",
        }

    # Search mode is intentionally unsupported; required abstract methods
    # return None so the framework falls back to latest.
    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    # --- latest mode (homepage, page 1) ---
    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(self.base_url, headers=self.headers, timeout=30)

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE_URL, href)
            # Drop fragments + queries before the canonical check; preserve
            # the bare canonical URL (slashless) afterwards for dedup/caching.
            bare = full.split("?", 1)[0].split("#", 1)[0].rstrip("/")
            if not bare:
                continue
            if _ASSET_EXT_RE.search(bare):
                continue
            path = bare[len(_BASE_URL):] if bare.startswith(_BASE_URL) else bare
            if path in {"", "/"}:
                continue
            if any(path.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
                continue
            if not _ARTICLE_RE.match(bare):
                continue
            links.add(bare)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("Independen empty article body: %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            logging.warning("Independen missing title: %s", link)
            return

        publish_date = self._extract_date(soup)
        if not publish_date:
            logging.warning("Independen missing date: %s", link)
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        content = self._extract_content(soup)
        if not content:
            logging.warning("Independen empty content: %s", link)
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
            "source": _SOURCE_LABEL,
            "link": link,
        })

    @staticmethod
    def _extract_title(soup):
        el = soup.select_one('meta[property="og:title"]')
        if el and el.get("content"):
            text = el["content"].strip()
            if text.endswith(_TITLE_SUFFIX):
                text = text[: -len(_TITLE_SUFFIX)].strip()
            return text
        h1 = soup.select_one("article h1") or soup.select_one("h1")
        if h1:
            return h1.get_text(strip=True)
        return ""

    @staticmethod
    def _extract_date(soup):
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            return _parse_iso(meta["content"])
        time_el = soup.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            return _parse_iso(time_el["datetime"])
        return None

    @staticmethod
    def _extract_author(soup):
        meta = soup.select_one('meta[name="author"]')
        if meta and meta.get("content"):
            text = meta["content"].strip()
            if text:
                return text
        author_el = soup.select_one(".field-name-author, .byline, .author")
        if author_el:
            text = author_el.get_text(" ", strip=True)
            # Strip common "Oleh:" prefixes occasionally present.
            text = re.sub(r"^oleh\s*:\s*", "", text, flags=re.IGNORECASE).strip()
            if text:
                return text
        return "Unknown"

    @staticmethod
    def _extract_category(soup):
        meta = soup.select_one('meta[property="article:section"]')
        if meta and meta.get("content"):
            text = meta["content"].strip()
            if text:
                return text
        crumb = soup.select_one(".breadcrumb a, nav.breadcrumb a")
        if crumb:
            text = crumb.get_text(strip=True)
            if text:
                return text
        return "Unknown"

    @staticmethod
    def _extract_content(soup):
        for tag in soup(
            ["script", "style", "noscript", "iframe", "aside", "form", "ins"]
        ):
            tag.decompose()

        article = soup.select_one("article")
        if not article:
            return ""

        # Drop share/related/footer blocks before paragraph collection.
        for cls_pattern in (
            "share", "social", "related", "popular", "sidebar",
            "newsletter", "subscribe", "comment", "promoted",
            "breadcrumb", "footer", "tags", "author-box",
        ):
            for tag in article.find_all(
                attrs={"class": re.compile(cls_pattern, re.IGNORECASE)}
            ):
                tag.decompose()

        paragraphs = []
        for p in article.find_all("p"):
            text = p.get_text(" ", strip=True)
            if text and len(text) >= 25:
                paragraphs.append(text)
        if not paragraphs:
            return ""
        return re.sub(r"\s+", " ", " ".join(paragraphs)).strip()
