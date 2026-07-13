"""
Hukumonline (hukumonline.com) scraper — latest-only.

Verified endpoints (2026-07-12):
    latest: https://www.hukumonline.com/berita/sitemap.xml  (XML urlset, page 1)
    article: https://www.hukumonline.com/berita/a/<slug>   (canonical free article)

Search stays disabled: bare GET, JSON Accept + no-cache, and Referer/cookie-
context GETs against the public /search endpoint all returned HTTP 401 with
`{"error": true}` — the search endpoint requires authenticated/legal-database
session cookies. Adding search would require credentials, so the scraper
remains latest-only via the public sitemap.
"""
import json
import logging
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class HukumonlineScraper(BaseScraper):
    """Hukumonline latest-only scraper.

    Only canonical free article paths under ``/berita/a/`` are accepted.
    Photo galleries (``/berita/foto``) and long-form stories
    (``/stories``) are explicitly excluded.
    """

    BASE_URL = "https://www.hukumonline.com"
    SITEMAP_URL = "https://www.hukumonline.com/berita/sitemap.xml"

    ARTICLE_RE = re.compile(
        r"^https?://(?:www\.)?hukumonline\.com/berita/a/[a-z0-9][a-z0-9-]*"
        r"(?:/[a-z0-9][a-z0-9-]*)*/?$",
        re.IGNORECASE,
    )
    EXCLUDE_RE = re.compile(r"/berita/(?:foto|stories)/", re.IGNORECASE)

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = self.BASE_URL
        self.start_date = start_date
        self.max_latest_pages = 1
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    # Search is unsupported for Hukumonline — required abstract methods return None.
    async def build_search_url(self, keyword, page):
        logging.info("Hukumonline: search unsupported; /search is legal-database SPA")
        return None

    def parse_article_links(self, response_text):
        return None

    # Latest path: page 1 of /berita/sitemap.xml only.
    async def build_latest_url(self, page):
        if page > 1:
            return None
        return await self.fetch(
            self.SITEMAP_URL,
            headers=self.headers,
            timeout=30,
        )

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None

        # Quick guard: Cloudflare challenge pages return HTML, not XML.
        head = response_text.lstrip()[:64].lower()
        if not head.startswith("<?xml") and "<urlset" not in head:
            logging.warning(
                "Hukumonline sitemap returned non-XML payload (likely Cloudflare challenge)"
            )
            return None

        try:
            root = ET.fromstring(response_text)
        except ET.ParseError as e:
            logging.error("Hukumonline sitemap parse error: %s", e)
            return None

        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        links = []
        for url in root.findall(".//sm:url/sm:loc", ns):
            loc = (url.text or "").strip().rstrip("/")
            if not loc:
                continue
            if self.EXCLUDE_RE.search(loc):
                continue
            if self.ARTICLE_RE.match(loc + "/"):
                links.append(loc)
        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self.headers, timeout=30)
        if not response_text:
            logging.warning("Hukumonline no response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            return

        publish_date = self._extract_date(soup, link)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        author, section = self._extract_author_section(soup)
        content = self._extract_content(soup)
        if not content:
            return

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": section or "berita",
            "source": "hukumonline.com",
            "link": link,
        }
        await self.queue_.put(item)

    @staticmethod
    def _extract_title(soup):
        meta = soup.find("meta", {"property": "og:title"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        h1 = soup.select_one("h1")
        if h1:
            return h1.get_text(strip=True)
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return ""

    def _extract_date(self, soup, link):
        # JSON-LD first
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload = self._parse_ld_json(script.string)
            for node in self._iter_ld_nodes(payload):
                dt = node.get("datePublished") or node.get("dateCreated")
                if dt:
                    parsed = self.parse_date(dt)
                    if parsed:
                        return parsed

        # meta fallback
        meta = soup.find("meta", {"property": "article:published_time"})
        if meta and meta.get("content"):
            parsed = self.parse_date(meta["content"])
            if parsed:
                return parsed

        # <time datetime="...">
        t = soup.select_one("time[datetime]")
        if t and t.get("datetime"):
            parsed = self.parse_date(t["datetime"])
            if parsed:
                return parsed

        logging.debug("Hukumonline date parse failed | url: %s", link)
        return None

    @staticmethod
    def _parse_ld_json(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _iter_ld_nodes(payload):
        if payload is None:
            return
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph") or [node]
            for entry in graph:
                if isinstance(entry, dict):
                    yield entry

    def _extract_author_section(self, soup):
        author = "Unknown"
        section = ""

        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload = self._parse_ld_json(script.string)
            for node in self._iter_ld_nodes(payload):
                if node.get("@type") not in ("NewsArticle", "Article", "WebPage"):
                    continue
                author_node = node.get("author")
                if isinstance(author_node, dict) and author_node.get("name"):
                    author = author_node["name"].strip()
                elif isinstance(author_node, list) and author_node:
                    first = author_node[0]
                    if isinstance(first, dict) and first.get("name"):
                        author = first["name"].strip()
                if not section:
                    sec = node.get("articleSection")
                    if isinstance(sec, str):
                        section = sec.strip()
                    elif isinstance(sec, list) and sec:
                        section = str(sec[0]).strip()

        if author == "Unknown":
            meta = soup.find("meta", {"name": "author"})
            if meta and meta.get("content"):
                author = meta["content"].strip()
        if not section:
            meta = soup.find("meta", {"property": "article:section"})
            if meta and meta.get("content"):
                section = meta["content"].strip()

        return author or "Unknown", section

    @staticmethod
    def _extract_content(soup):
        body = (
            soup.select_one("article")
            or soup.select_one("div.article-content")
            or soup.select_one("div.entry-content")
            or soup.select_one("main")
        )
        if not body:
            return ""

        for tag in body.find_all(["script", "style", "iframe", "noscript"]):
            tag.extract()
        for tag in body.find_all(
            ["section", "div", "aside"],
            class_=re.compile(
                r"related|sidebar|footer|nav|promo|share|social|comment",
                re.IGNORECASE,
            ),
        ):
            tag.extract()

        paragraphs = []
        for p in body.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) > 30:
                paragraphs.append(text)

        content = " ".join(paragraphs).strip()
        if content:
            return content

        return body.get_text(" ", strip=True)
