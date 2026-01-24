import json
import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TirtoScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://tirto.id"
        self.start_date = start_date
        self.continue_scraping = True

        self._search_url = f"{self.base_url}/search"

    async def build_search_url(self, keyword, page):
        kw = quote_plus((keyword or "").strip())
        url = f"{self._search_url}?q={kw}&page={page}"
        return await self.fetch(url, timeout=30)

    def parse_article_links(self, response_text):
        if not response_text:
            return None

        soup = BeautifulSoup(response_text, "html.parser")
        links = set()
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue

            if href.startswith("/"):
                href = f"{self.base_url}{href}"

            if not href.startswith(self.base_url):
                continue

            # Avoid obvious non-article URLs
            if "/search" in href or href.rstrip("/") == self.base_url:
                continue

            # Avoid non-article sections.
            if re.search(
                r"/insider/|/kueri$|/news$|/inception$|/visual-tirto/|/diajeng/|/bisnis-tirto/",
                href,
            ):
                continue

            # Heuristic: most articles end with a short id slug like -hxxxx
            if not re.search(r"-[a-zA-Z0-9]{4,6}$", href.rstrip("/")):
                continue

            links.add(href)

        return links or None

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link, timeout=30)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")
        try:
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                og_title = soup.select_one("meta[property='og:title']")
                if og_title and og_title.get("content"):
                    title = og_title.get("content").strip()
            if not title:
                return

            author_el = soup.select_one("meta[name='author']")
            author = (
                author_el.get("content").strip()
                if author_el and author_el.get("content")
                else "Unknown"
            )

            publish_date_str = ""
            for sc in soup.select("script"):
                txt = (sc.string or sc.get_text() or "").strip()
                if not txt.startswith("[") or "schema.org" not in txt:
                    continue
                try:
                    data = json.loads(txt)
                except Exception:
                    continue

                def walk(x):
                    if isinstance(x, dict):
                        if x.get("@type") in ("NewsArticle", "Article"):
                            return x
                        for v in x.values():
                            r = walk(v)
                            if r:
                                return r
                    elif isinstance(x, list):
                        for v in x:
                            r = walk(v)
                            if r:
                                return r
                    return None

                art = walk(data)
                if art:
                    publish_date_str = (
                        art.get("datePublished")
                        or art.get("dateCreated")
                        or art.get("dateModified")
                        or ""
                    )
                if publish_date_str:
                    break

            content_div = soup.select_one("article")
            if not content_div:
                content_div = soup.select_one("[itemprop='articleBody']")
            if not content_div:
                return

            paragraphs = [p.get_text(" ", strip=True) for p in content_div.select("p")]
            paragraphs = [p for p in paragraphs if len(p) > 40]
            content = " ".join(paragraphs).strip()
            if not content:
                return

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    "Tirto date parse failed | url: %s | date: %r",
                    link,
                    publish_date_str[:50],
                )
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
                "category": "Unknown",
                "source": "tirto.id",
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error("Error parsing article %s: %s", link, e)
