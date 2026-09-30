"""Unregistered, first-page-only Harian Rakyat Aceh .com adapter."""

import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import quote, urljoin, urlsplit

import aiohttp
from bs4 import BeautifulSoup

from ..timeutils import to_project_naive
from ..utils import _looks_blocked
from .basescraper import BaseScraper


class RakyatAcehScraper(BaseScraper):
    base_url = "https://harianrakyataceh.com"
    user_agent = "news-watch-reassessment/1.0"
    max_bytes = 262144
    article_path = re.compile(r"/news/[a-z0-9-]+/index\.html$")

    def __init__(self, keywords, concurrency=1, start_date=None, queue_=None,
                 sample_limit=3, **kwargs):
        # The registry supplies keyword_concurrency=1; keep it serial without
        # forwarding the same keyword twice to BaseScraper.
        kwargs.pop("keyword_concurrency", None)
        super().__init__(keywords, concurrency=1, queue_=queue_, max_pages=1,
                         max_latest_pages=1, keyword_concurrency=1, **kwargs)
        self.start_date = start_date
        self.sample_limit = min(max(1, sample_limit), 3)
        self._request_lock = asyncio.Lock()
        self._last_start = None
        self.request_receipts = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            auto_decompress=False,
            trust_env=False,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"},
        )
        return self

    def _article_url(self, href):
        url = urljoin(self.base_url + "/", href)
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.netloc == "harianrakyataceh.com" and not parts.query and not parts.fragment and self.article_path.fullmatch(parts.path):
            return url
        return None

    async def fetch(self, url, method="GET", data=None, headers=None, retries=0, timeout=20):
        parts = urlsplit(url)
        if method != "GET" or parts.scheme != "https" or parts.netloc != "harianrakyataceh.com" or not self.session:
            return None
        async with self._request_lock:
            loop = asyncio.get_running_loop()
            if self._last_start is not None:
                await asyncio.sleep(max(0, 10 - (loop.time() - self._last_start)))
            self._last_start = loop.time()
            receipt = {"url": url, "start_monotonic": self._last_start, "status": None,
                       "bytes": 0, "outcome": "failed"}
            self.request_receipts.append(receipt)
            try:
                async with self.session.get(url, allow_redirects=False,
                                            timeout=aiohttp.ClientTimeout(total=20)) as response:
                    receipt["status"] = response.status
                    if response.status != 200:
                        receipt["outcome"] = "http_status"
                        return None
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        receipt["outcome"] = "unsupported_encoding"
                        return None
                    chunks = []
                    remaining = self.max_bytes
                    while True:
                        chunk = await response.content.read(min(65536, remaining + 1))
                        if not chunk:
                            break
                        receipt["bytes"] += len(chunk)
                        if receipt["bytes"] > self.max_bytes:
                            receipt["outcome"] = "oversized"
                            return None
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    raw = b"".join(chunks)
                    text = raw.decode(response.charset or "utf-8", errors="replace")
                    if len(text.encode("utf-8")) > self.max_bytes:
                        receipt["outcome"] = "oversized_decoded"
                        return None
                    if _looks_blocked(text):
                        receipt["outcome"] = "possible_challenge"
                        return None
                    receipt["outcome"] = "ok"
                    return text
            except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError, LookupError) as exc:
                receipt["outcome"] = type(exc).__name__
                logging.warning("Rakyat Aceh request failed: %s", exc)
                return None

    async def build_search_url(self, keyword, page):
        if page != 1:
            return None
        return await self.fetch(f"{self.base_url}/search/?q={quote(keyword)}")

    async def build_latest_url(self, page):
        return await self.fetch(self.base_url + "/") if page == 1 else None

    def _cards(self, container):
        links = []
        if container:
            for article in container.select("article"):
                anchor = article.select_one("a.title[href]")
                stamp = article.select_one("time[datetime]")
                if not anchor or not stamp:
                    continue
                try:
                    date = datetime.fromisoformat(stamp["datetime"])
                except ValueError:
                    continue
                if date.tzinfo is None:
                    continue
                url = self._article_url(anchor["href"])
                if url and url not in links:
                    links.append(url)
        return links[:self.sample_limit]

    def parse_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        container = soup.select_one("main > .row > .col-md-8")
        return self._cards(container) or None

    def parse_latest_article_links(self, response_text):
        if not response_text:
            return None
        soup = BeautifulSoup(response_text, "html.parser")
        for block in soup.select("main .block"):
            title = block.find("div", class_="block-title", recursive=False)
            if title and title.get_text(" ", strip=True) == "Berita Terkini":
                content = block.find("div", class_="block-content", recursive=False)
                return self._cards(content) or None
        return None

    async def get_article(self, link, keyword):
        if not self._article_url(link):
            return
        html = await self.fetch(link)
        if not html:
            return
        soup = BeautifulSoup(html, "html.parser")
        detail = soup.select_one("main article > .detail")
        if not detail:
            return
        canonical = soup.select_one('link[rel="canonical"][href]')
        if not canonical or canonical["href"] != link:
            return
        # Never emit a partial body when the publisher indicates continuation.
        if detail.select('a[rel="next"], a[href*="/page/"], .pagination a, .page-links a'):
            return
        heading = detail.select_one("h1")
        stamp = detail.select_one(".meta-post time[datetime]")
        body = detail.select_one(".the-content")
        if not heading or not stamp or not body:
            return
        try:
            published = datetime.fromisoformat(stamp["datetime"])
        except ValueError:
            return
        if published.tzinfo is None:
            return
        published = to_project_naive(published)
        if self.start_date and published < self.start_date:
            return
        if self.start_datetime and published < self.start_datetime:
            return
        if self.end_datetime and published > self.end_datetime:
            return
        paragraphs = [p.get_text(" ", strip=True) for p in body.select("p")]
        content = "\n\n".join(p for p in paragraphs if p)
        title = heading.get_text(" ", strip=True)
        if not title or not content:
            return
        if keyword != "latest" and not all(
            token.lower() in (title + " " + content).lower() for token in keyword.split()
        ):
            return
        category = detail.select_one(".category")
        await self.queue_.put({"title": title, "publish_date": published,
                               "author": "Unknown", "content": content,
                               "keyword": keyword, "category": category.get_text(" ", strip=True) if category else "Unknown",
                               "source": "harianrakyataceh.com", "link": link})
