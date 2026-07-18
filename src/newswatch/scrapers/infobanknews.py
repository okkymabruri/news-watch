"""Infobanknews (infobanknews.com) scraper.

Discovery:
    search : https://infobanknews.com/wp-json/wp/v2/posts?search={kw}&per_page=20&page={n}&_fields=link
    latest : https://infobanknews.com/wp-json/wp/v2/posts?per_page=20&page={n}&_fields=link

The WordPress REST endpoint returns JSON directly, so we skip the
client-rendered search HTML. ``_fields=link`` keeps payloads small and
forces canonical post URLs only. ``_embed``/``_fields=*`` are intentionally
not requested.

Article URL pattern: ``https://infobanknews.com/<slug>/`` (one root-level
slug segment). Taxonomy (``/category/``, ``/tag/``, ``/author/``),
``/wp-`` admin/static, and ``/feed`` paths are rejected up front.
"""

import json
import logging
import re
from html import unescape
from urllib.parse import quote

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class InfobanknewsScraper(BaseScraper):
    """Infobanknews scraper driven by the public WordPress REST API."""

    BASE_URL = "https://infobanknews.com"
    REST_URL = "https://infobanknews.com/wp-json/wp/v2/posts"
    SOURCE_LABEL = "infobanknews.com"
    MAX_SEARCH_PAGES = 10

    ARTICLE_RE = re.compile(
        r"^https?://(?:www\.)?infobanknews\.com/"
        r"(?!wp-|category/|tag/|author/|feed(?:/|$))[a-z0-9][a-z0-9-]*/?$",
        re.IGNORECASE,
    )

    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = self.BASE_URL
        self.start_date = start_date
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.5",
        }
        self._json_headers = {**self.headers, "Accept": "application/json"}
        self._html_headers = {
            **self.headers,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    async def build_search_url(self, keyword, page):
        if page < 1 or page > self.MAX_SEARCH_PAGES:
            return None
        url = (
            f"{self.REST_URL}?search={quote(keyword, safe='')}"
            f"&per_page=20&page={page}&_fields=link"
        )
        return await self.fetch(url, headers=self._json_headers, timeout=30)

    async def build_latest_url(self, page):
        if page < 1:
            return None
        url = f"{self.REST_URL}?per_page=20&page={page}&_fields=link"
        return await self.fetch(url, headers=self._json_headers, timeout=30)

    def parse_article_links(self, response_text):
        return self._parse_rest_links(response_text)

    def parse_latest_article_links(self, response_text):
        return self._parse_rest_links(response_text)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, headers=self._html_headers, timeout=30)
        if not response_text:
            logging.warning("Infobanknews no response for %s", link)
            return

        soup = BeautifulSoup(response_text, "html.parser")

        title = self._extract_title(soup)
        if not title:
            logging.debug("Infobanknews title missing for %s", link)
            return

        publish_date = self._extract_date(soup, link)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        author, category = self._extract_author_category(soup, link)
        content = self._extract_content(soup)
        if not content:
            logging.debug("Infobanknews content empty for %s", link)
            return

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category or "uncategorized",
            "source": self.SOURCE_LABEL,
            "link": link,
        }
        await self.queue_.put(item)

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------
    def _parse_rest_links(self, response_text):
        if not response_text:
            return None

        head = response_text.lstrip()[:64]
        if not (head.startswith("[") or head.startswith("{")):
            logging.warning(
                "Infobanknews REST returned non-JSON payload (head=%r)",
                head[:32],
            )
            return None

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as e:
            logging.error("Infobanknews REST JSON parse error: %s", e)
            return None

        if not isinstance(payload, list):
            return None

        links = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            link = entry.get("link")
            if not isinstance(link, str):
                continue
            link = link.strip()
            if not link:
                continue
            if not self.ARTICLE_RE.match(link):
                continue
            normalized = link if link.endswith("/") else link + "/"
            links.append(normalized)
        return links or None

    # ------------------------------------------------------------------
    # Article extraction
    # ------------------------------------------------------------------
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
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload = self._parse_ld_json(script.string)
            for node in self._iter_ld_nodes(payload):
                if not isinstance(node, dict):
                    continue
                dt = node.get("datePublished") or node.get("dateCreated")
                parsed = self._parse_iso_date(dt)
                if parsed:
                    return parsed

        meta = soup.find("meta", {"property": "article:published_time"})
        if meta and meta.get("content"):
            parsed = self._parse_iso_date(meta["content"])
            if parsed:
                return parsed

        t = soup.select_one("time[datetime]")
        if t and t.get("datetime"):
            parsed = self._parse_iso_date(t["datetime"])
            if parsed:
                return parsed

        meta_name = soup.find(
            "meta", {"name": re.compile(r"^date.*", re.IGNORECASE)}
        )
        if meta_name and meta_name.get("content"):
            parsed = self._parse_iso_date(meta_name["content"])
            if parsed:
                return parsed

        logging.debug("Infobanknews date parse failed | url: %s", link)
        return None

    def _parse_iso_date(self, raw):
        if not raw or not isinstance(raw, str):
            return None
        parsed = self.parse_date(raw)
        return parsed

    def _extract_author_category(self, soup, link):
        author = "Unknown"
        category = ""

        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload = self._parse_ld_json(script.string)
            for node in self._iter_ld_nodes(payload):
                if not isinstance(node, dict):
                    continue
                if author == "Unknown":
                    author = self._author_from_ld(node) or author
                if not category:
                    category = self._category_from_ld(node)
        if author == "Unknown":
            author = self._author_from_meta(soup)
        if not category:
            category = self._category_from_meta(soup, link)
        return author or "Unknown", category

    @staticmethod
    def _author_from_ld(node):
        author_node = node.get("author")
        if isinstance(author_node, dict):
            name = author_node.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        if isinstance(author_node, list) and author_node:
            first = author_node[0]
            if isinstance(first, dict):
                name = first.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        if isinstance(author_node, str) and author_node.strip():
            return author_node.strip()
        return ""

    @staticmethod
    def _author_from_meta(soup):
        for attr in (
            {"name": "author"},
            {"name": "byline"},
            {"property": "article:author"},
            {"name": "dc.creator"},
        ):
            meta = soup.find("meta", attr)
            if meta and meta.get("content"):
                value = meta["content"].strip()
                if value:
                    return value
        return "Unknown"

    @staticmethod
    def _category_from_ld(node):
        section = node.get("articleSection")
        if isinstance(section, str) and section.strip():
            return section.strip()
        if isinstance(section, list) and section:
            first = section[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
            if isinstance(first, dict):
                name = first.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        about = node.get("about")
        if isinstance(about, str) and about.strip():
            return about.strip()
        if isinstance(about, list) and about:
            first = about[0]
            if isinstance(first, dict):
                name = first.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        return ""

    @staticmethod
    def _category_from_meta(soup, link):
        meta = soup.find("meta", {"property": "article:section"})
        if meta and meta.get("content"):
            value = meta["content"].strip()
            if value:
                return value
        meta = soup.find("meta", {"name": "article:section"})
        if meta and meta.get("content"):
            value = meta["content"].strip()
            if value:
                return value

        for script in soup.find_all("script", {"type": "application/ld+json"}):
            payload_text = script.string or script.get_text()
            payload = InfobanknewsScraper._parse_ld_json(payload_text)
            if not payload:
                continue
            for node in InfobanknewsScraper._iter_ld_nodes(payload):
                if not isinstance(node, dict):
                    continue
                if "BreadcrumbList" in str(node.get("@type", "")):
                    for item in node.get("itemListElement", []) or []:
                        if not isinstance(item, dict):
                            continue
                        nested = item.get("item") or {}
                        if isinstance(nested, dict):
                            name = nested.get("name")
                        else:
                            name = item.get("name")
                        if isinstance(name, str) and name.strip() and name.strip().lower() != "home":
                            return name.strip()

        nav = soup.select_one("nav.breadcrumb, ol.breadcrumb, ul.breadcrumb")
        if nav:
            items = [
                li.get_text(strip=True)
                for li in nav.find_all(["a", "span"])
                if li.get_text(strip=True)
            ]
            if items:
                return items[-1]

        return ""

    def _extract_content(self, soup):
        body = (
            soup.select_one("div.article-content")
            or soup.select_one("article")
            or soup.select_one("div.entry-content")
            or soup.select_one("main")
        )
        if not body:
            return ""

        for tag in body.find_all(["script", "style", "iframe", "noscript"]):
            tag.extract()
        for tag in body.find_all(
            ["section", "div", "aside", "ul"],
            class_=re.compile(
                r"related|sidebar|footer|nav|promo|share|social|comment|tag-list|advert",
                re.IGNORECASE,
            ),
        ):
            tag.extract()

        paragraphs = []
        for p in body.find_all("p"):
            text = p.get_text(" ", strip=True)
            text = unescape(text)
            if len(text) > 30:
                paragraphs.append(text)

        content = " ".join(paragraphs).strip()
        if content:
            return content
        fallback = body.get_text(" ", strip=True)
        return unescape(fallback)

    # ------------------------------------------------------------------
    # JSON-LD helpers (shared with other scrapers' style but bounded here)
    # ------------------------------------------------------------------
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
        candidates = payload if isinstance(payload, list) else [payload]
        for node in candidates:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph") or node
            entries = graph if isinstance(graph, list) else [graph]
            for entry in entries:
                if isinstance(entry, dict):
                    yield entry
