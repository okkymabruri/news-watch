import logging
import json
import re
from urllib.parse import urlencode

from rnet import Client
from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class CNBCScraper(BaseScraper):
    def __init__(self, keywords, concurrency=12, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.cnbcindonesia.com"
        self.start_date = start_date
        self.max_pages = 10

    async def _fetch_rnet(
        self,
        url: str,
        *,
        headers: dict | None = None,
        timeout: int = 30,
    ) -> str | None:
        try:
            async with Client() as client:
                resp = await client.get(url, headers=headers, timeout=timeout)
                if resp.status != 200:
                    return None
                text = await resp.text()
                return text or None
        except Exception as e:
            logging.debug(f"rnet fetch failed for {url}: {e}")
            return None

    async def build_search_url(self, keyword, page):
        # https://www.cnbcindonesia.com/search?query=&fromdate=&page=
        query_params = {
            "query": keyword,
            "fromdate": self.start_date.strftime("%Y/%m/%d"),
            "page": page,
        }
        url = f"{self.base_url}/search?{urlencode(query_params)}"
        text = await self.fetch(url)
        if text:
            return text
        return await self._fetch_rnet(url)

    async def _fetch_rss_links(self, keyword):
        # Reliable fallback in environments where HTML search gets blocked.
        rss_url = f"{self.base_url}/rss?{urlencode({'tag': keyword})}"
        rss_text = await self.fetch(
            rss_url,
            headers={"Accept": "application/xml,*/*", "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        if not rss_text:
            rss_text = await self._fetch_rnet(
                rss_url,
                headers={"Accept": "application/xml,*/*", "User-Agent": "Mozilla/5.0"},
                timeout=30,
            )
        if not rss_text:
            return None

        soup = BeautifulSoup(rss_text, "xml")
        links = {
            (item.link.get_text(strip=True) if item.link else "")
            for item in soup.select("item")
        }
        links = {link for link in links if link.startswith("http")}

        # CNBC RSS sometimes includes non-searchable content (e.g. video pages).
        article_href = re.compile(
            r"^https?://www\.cnbcindonesia\.com/.+?/\d{8}-\d+-\d+/"
        )
        links = {link for link in links if article_href.search(link)}
        return links or None

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        articles = soup.select(".nhl-list a.group[href]")
        if not articles:
            return None

        filtered_hrefs = {a.get("href") for a in articles if a.get("href")}
        return filtered_hrefs

    async def fetch_search_results(self, keyword):
        # Prefer HTML search (richer + supports date filter), but fall back to RSS when blocked.
        page = 1
        while self.continue_scraping and page <= self.max_pages:
            response_text = await self.build_search_url(keyword, page)
            if not response_text:
                break

            filtered_hrefs = self.parse_article_links(response_text)
            if not filtered_hrefs:
                # Some environments return HTML that isn't detected as blocked but doesn't contain results.
                # Retry once via rnet before giving up on HTML search.
                url = f"{self.base_url}/search?{urlencode({'query': keyword, 'fromdate': self.start_date.strftime('%Y/%m/%d'), 'page': page})}"
                response_text = await self._fetch_rnet(url)
                if response_text:
                    filtered_hrefs = self.parse_article_links(response_text)
            if not filtered_hrefs:
                break

            continue_scraping = await self.process_page(filtered_hrefs, keyword)
            if not continue_scraping:
                return

            page += 1

        rss_links = await self._fetch_rss_links(keyword)
        if not rss_links:
            logging.info(f"No news found on {self.base_url} for keyword: '{keyword}'")
            return

        await self.process_page(rss_links, keyword)

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            response_text = await self._fetch_rnet(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")

        # JSON-LD fallback (more stable across templates / A/B variants)
        ld_json = None
        for sc in soup.select("script[type='application/ld+json']"):
            raw = (sc.string or sc.get_text() or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue

            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("@type") in ("NewsArticle", "Article"):
                    ld_json = node
                    break
                graph = node.get("@graph")
                if isinstance(graph, list):
                    for g in graph:
                        if isinstance(g, dict) and g.get("@type") in (
                            "NewsArticle",
                            "Article",
                        ):
                            ld_json = g
                            break
                if ld_json:
                    break
            if ld_json:
                break

        try:
            category_el = soup.select_one("a.text-xs.font-semibold[href='#']")
            title_el = soup.select_one("h1.mb-4.text-32.font-extrabold")
            author_els = soup.select("div.mb-1.text-base.font-semibold")
            date_el = soup.select_one("div.text-cm.text-gray")
            content_div = soup.find("div", {"class": "detail-text"})

            category = category_el.get_text(strip=True) if category_el else ""
            title = title_el.get_text(strip=True) if title_el else ""
            author = author_els[1].get_text(strip=True) if len(author_els) > 1 else ""
            publish_date_str = date_el.get_text(strip=True) if date_el else ""

            content = ""
            if content_div:
                # loop through paragraphs and remove those with class patterns like "sisip-*"
                for tag in content_div.find_all(["table", "div"]):
                    class_list = tag.get("class", [])
                    if any(
                        cls.startswith("sisip_") or cls.startswith("link_sisip")
                        for cls in class_list
                    ):
                        tag.extract()
                content = content_div.get_text(separator="\n", strip=True)

            if ld_json:
                title = title or (ld_json.get("headline") or "").strip()
                category = category or (ld_json.get("articleSection") or "").strip()
                publish_date_str = publish_date_str or (
                    ld_json.get("datePublished")
                    or ld_json.get("dateCreated")
                    or ld_json.get("dateModified")
                    or ""
                )
                if not author:
                    a = ld_json.get("author")
                    if isinstance(a, dict):
                        author = (a.get("name") or "").strip()
                    elif isinstance(a, list) and a:
                        first = a[0]
                        if isinstance(first, dict):
                            author = (first.get("name") or "").strip()
                        elif isinstance(first, str):
                            author = first.strip()
                if not content:
                    body = ld_json.get("articleBody")
                    if isinstance(body, str):
                        content = body.strip()

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(f"Error parsing date for article {link}")
                return
            if not title or not content:
                logging.error(f"Error parsing article {link}: missing title/content")
                return
            if self.start_date and publish_date < self.start_date:
                self.continue_scraping = False
                return

            item = {
                "title": title,
                "publish_date": publish_date,
                "author": author,
                "content": content,
                "keyword": keyword,
                "category": category,
                "source": self.base_url.split("www.")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}")
