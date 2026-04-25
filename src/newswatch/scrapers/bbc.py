import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class BBCNewsScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.bbc.com"
        self.start_date = start_date
        self.continue_scraping = True
        self.max_pages = 10

    async def build_search_url(self, keyword, page):
        url = f"{self.base_url}/search?{urlencode({'q': keyword, 'page': page})}"
        return await self.fetch(url, timeout=30)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None

        try:
            data = json.loads(script.string)
            page_data = data.get("props", {}).get("pageProps", {}).get("page", {})
        except json.JSONDecodeError:
            return None

        results = []
        for v in page_data.values():
            if isinstance(v, dict) and "results" in v:
                results = v["results"]
                break

        if not results:
            return None

        filtered_hrefs = set()
        for r in results:
            meta = r.get("metadata", {})
            if meta.get("contentType") != "article" or meta.get("subtype") != "news":
                continue
            # Filter by date if start_date is set
            if self.start_date:
                first_updated = meta.get("firstUpdated")
                if first_updated:
                    article_date = datetime.fromtimestamp(first_updated / 1000, tz=timezone.utc).replace(tzinfo=None)
                    if article_date < self.start_date:
                        continue
            href = r.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"
            filtered_hrefs.add(href)

        return filtered_hrefs or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return

        try:
            data = json.loads(script.string)
            page_data = data.get("props", {}).get("pageProps", {}).get("page", {})
            article_data = list(page_data.values())[0] if page_data else {}
        except (json.JSONDecodeError, IndexError):
            return

        contents = article_data.get("contents", [])
        if not contents:
            return

        title = ""
        paragraphs = []
        authors = []
        publish_ts = None

        for block in contents:
            btype = block.get("type", "")
            model = block.get("model", {})

            if btype == "headline" and not title:
                text_model = model.get("text", "")
                if text_model:
                    title = text_model.strip()
                else:
                    # Nested headline: model -> blocks -> model -> blocks -> model -> text
                    for hb in model.get("blocks", []):
                        if hb.get("type") != "text":
                            continue
                        hmodel = hb.get("model", {})
                        text = hmodel.get("text", "").strip()
                        if text:
                            title = text
                            break
                        # Deeper nesting
                        for nb in hmodel.get("blocks", []):
                            if nb.get("type") == "paragraph":
                                t = nb.get("model", {}).get("text", "").strip()
                                if t:
                                    title = t
                                    break
                        if title:
                            break

            elif btype == "timestamp" and publish_ts is None:
                publish_ts = model.get("timestamp")

            elif btype == "byline":
                authors = self._extract_authors(model)

            elif btype == "text":
                blocks = model.get("blocks", [])
                for b in blocks:
                    if b.get("type") == "paragraph":
                        text_model = b.get("model", {})
                        text = text_model.get("text", "").strip()
                        if text:
                            paragraphs.append(text)

        if not title:
            return

        content = " ".join(paragraphs)
        if not content:
            return

        publish_date = None
        if publish_ts:
            publish_date = datetime.fromtimestamp(publish_ts / 1000, tz=timezone.utc).replace(tzinfo=None)
        if not publish_date:
            return

        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        author = ", ".join(authors) if authors else "Unknown"

        # Extract category from URL path
        path = link.replace(self.base_url, "").strip("/")
        category = path.split("/")[0] if path else ""

        item = {
            "title": title,
            "publish_date": publish_date,
            "author": author,
            "content": content,
            "keyword": keyword,
            "category": category,
            "source": "bbc.com",
            "link": link,
        }
        await self.queue_.put(item)

    def _extract_authors(self, byline_model):
        names = []
        blocks = byline_model.get("blocks", [])
        for contributor in blocks:
            if contributor.get("type") != "contributor":
                continue
            cblocks = contributor.get("model", {}).get("blocks", [])
            for cb in cblocks:
                if cb.get("type") != "name":
                    continue
                nblocks = cb.get("model", {}).get("blocks", [])
                for nb in nblocks:
                    if nb.get("type") != "paragraph":
                        continue
                    for frag in nb.get("model", {}).get("blocks", []):
                        if frag.get("type") == "fragment":
                            name = frag.get("model", {}).get("text", "").strip()
                            if name:
                                names.append(name)
        return names
