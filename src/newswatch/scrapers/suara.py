"""Suara.com scraper — Playwright-rendered search with parser-side relevance filter.

The native /search page renders dated article anchors in the DOM for valid
queries. A nonsense keyword or a WAF/captcha page renders generic unrelated
dated anchors from across the network. We render the page in headless
Chromium, harvest every dated Suara network article anchor via the existing
URL matcher, dedupe, then drop candidates whose normalized keyword tokens
do not appear in the anchor title/text or URL slug. Generic unrelated
trending links therefore yield an empty set. jogja.suara.com and other
subdomains are accepted by the same network regex as www.suara.com.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .basescraper import BaseScraper


class SuaraScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.suara.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10
        self._article_href = re.compile(
            r"^https?://(?:[\w-]+\.)?suara\.com/.+/20\d{2}/\d{2}/\d{2}/.+"
        )
        self._ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )

    async def fetch_search_results(self, keyword):
        """Render the search page and harvest dated Suara article anchors."""
        url = f"{self.base_url}/search?q={quote(keyword, safe='')}"
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=self._ua)
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                except PlaywrightTimeoutError as exc:
                    logging.debug("Suara page load timed out for %r: %s", keyword, exc)
                    return
                except PlaywrightError as exc:
                    logging.debug("Suara page transport failed for %r: %s", keyword, exc)
                    return

                try:
                    await page.wait_for_timeout(3_000)
                    html = await page.content()
                except PlaywrightError as exc:
                    logging.debug("Suara content read failed for %r: %s", keyword, exc)
                    return

                links = self._harvest_links(html, keyword)
                if not links:
                    logging.info("No Suara news found for keyword: %r", keyword)
                    return
                await self.process_page(list(links), keyword)
            finally:
                await browser.close()

    # Fallbacks to satisfy BaseScraper abstract methods
    async def build_search_url(self, keyword, page):
        return None

    def parse_article_links(self, response_text):
        return None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            return

        soup = self._get_soup(response_text)
        try:
            title = self._extract_title(soup)
            if not title:
                return

            publish_date_str = self._extract_date_text(soup)
            publish_date = self.parse_date(publish_date_str, locales=["id"]) if publish_date_str else None
            if not publish_date:
                logging.debug(
                    "Suara date parse failed | url: %s | date: %r",
                    link,
                    (publish_date_str or "")[:50],
                )
                return

            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            content = self._extract_content(soup)
            if not content:
                return

            category = self._category_from_url(link)
            author = self._extract_author(soup) or "Unknown"

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": "suara.com",
                "link": link,
            }
            await self.queue_.put(item)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            logging.error("Error parsing article %s: %s", link, exc)

    # ── helpers ────────────────────────────────────────────────────────────

    def _harvest_links(self, html: str, keyword: str) -> set[str]:
        soup = self._get_soup(html)
        tokens = self._keyword_tokens(keyword)
        links: set[str] = set()
        for anchor in soup.select("a[href]"):
            if not isinstance(anchor, Tag):
                continue
            href = anchor.get("href", "")
            if not isinstance(href, str) or not self._article_href.match(href):
                continue
            slug = href.split("?", 1)[0].lower()
            title_text = anchor.get_text(" ", strip=True).lower()
            if not self._is_relevant(tokens, slug, title_text):
                continue
            links.add(slug)
        return links

    @staticmethod
    def _category_from_url(link: str) -> str:
        match = re.match(r"^https?://(?:[\w-]+\.)?suara\.com/([^/]+)/", link)
        if not match:
            return ""
        section = match.group(1).lower()
        if section in {"read", "search", "tag", "category", "author"}:
            return ""
        return section

    @staticmethod
    def _keyword_tokens(keyword: str) -> list[str]:
        normalized = re.sub(r"[^a-z0-9]+", " ", keyword.lower()).strip()
        return [tok for tok in normalized.split(" ") if tok]

    @staticmethod
    def _is_relevant(tokens: list[str], slug: str, title: str) -> bool:
        if not tokens:
            return False
        haystack = f"{slug} {title}"
        return any(tok in haystack for tok in tokens)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        og = soup.select_one('meta[property="og:title"]')
        if isinstance(og, Tag):
            content = og.get("content")
            if isinstance(content, str):
                cleaned = content.strip()
                if cleaned:
                    return cleaned
        h1 = soup.select_one("h1")
        if isinstance(h1, Tag):
            return h1.get_text(" ", strip=True)
        return ""

    def _extract_date_text(self, soup: BeautifulSoup) -> str:
        published = soup.select_one(
            'script[type="application/ld+json"]'
        )
        if isinstance(published, Tag):
            ld_text = published.get_text(" ", strip=True)
            match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', ld_text)
            if match:
                return match.group(1)

        for span in soup.select("span"):
            if not isinstance(span, Tag):
                continue
            text = span.get_text(" ", strip=True)
            if "WIB" in text and re.search(r"\d{4}", text):
                return text.split("|", 1)[0].strip()

        legacy = soup.select_one("span.mt-10")
        if isinstance(legacy, Tag):
            return legacy.get_text(" ", strip=True)

        legacy_date = soup.select_one("span[class*='date']")
        if isinstance(legacy_date, Tag):
            return legacy_date.get_text(" ", strip=True)

        return ""

    def _extract_content(self, soup: BeautifulSoup) -> str:
        body = soup.select_one("div.article-content")
        if not isinstance(body, Tag):
            body = soup.select_one("article.detail-content")
        if not isinstance(body, Tag):
            body = soup.select_one("div.detail-content")
        if not isinstance(body, Tag):
            return ""
        for noise in body.select("script, style, noscript, iframe"):
            noise.extract()
        paragraphs: list[str] = []
        for p in body.find_all("p"):
            if not isinstance(p, Tag):
                continue
            classes = p.get("class") or []
            if any("baca-juga" in c for c in classes):
                continue
            text = p.get_text(" ", strip=True)
            if len(text) > 30:
                paragraphs.append(text)
        return " ".join(paragraphs)

    def _extract_author(self, soup: BeautifulSoup) -> str:
        ld = soup.select_one('script[type="application/ld+json"]')
        if isinstance(ld, Tag):
            ld_text = ld.get_text(" ", strip=True)
            try:
                data = json.loads(ld_text)
            except (ValueError, json.JSONDecodeError):
                data = None
            name = self._author_from_ld(data)
            if name:
                return name

        meta = soup.select_one('meta[name="author"]')
        if isinstance(meta, Tag):
            content = meta.get("content")
            if isinstance(content, str):
                cleaned = content.strip()
                if cleaned:
                    return cleaned

        trigger = soup.select_one("a.author-trigger, .author-trigger a")
        if isinstance(trigger, Tag):
            return trigger.get_text(" ", strip=True)

        return ""

    @staticmethod
    def _author_from_ld(data) -> str:
        if isinstance(data, dict):
            author = data.get("author")
            if isinstance(author, dict):
                name = author.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            if isinstance(author, list) and author:
                first = author[0]
                if isinstance(first, dict):
                    name = first.get("name")
                    if isinstance(name, str) and name.strip():
                        return name.strip()
            graph = data.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if not isinstance(node, dict):
                        continue
                    if node.get("@type") in {"Person", "NewsArticle"}:
                        candidate = SuaraScraper._author_from_ld(node)
                        if candidate:
                            return candidate
        return ""

    def _get_soup(self, text: Optional[str]) -> BeautifulSoup:
        return BeautifulSoup(text or "", "html.parser")

    async def build_latest_url(self, page):
        if page > 1:
            return None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=self._ua)
                pg = await context.new_page()
                await pg.goto(self.base_url, wait_until="domcontentloaded", timeout=30_000)
                await pg.wait_for_timeout(3_000)
                return await pg.content()
            finally:
                await browser.close()

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = self._get_soup(response_text)
        links = set()
        for a in soup.select("a[href]"):
            if not isinstance(a, Tag):
                continue
            href = a.get("href", "")
            if not isinstance(href, str) or not self._article_href.match(href):
                continue
            links.add(href.split("?")[0])
        return links or None