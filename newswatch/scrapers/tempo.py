import json
import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class TempoScraper(BaseScraper):
    def __init__(self, keywords, concurrency=1, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.tempo.co"
        self.api_url = "https://www.tempo.co/api/gateway/articles"
        self.start_date = start_date

    async def build_search_url(self, keyword, page):
        # https://www.tempo.co/api/gateway/articles?status=published&tags%5B%5D=indonesia&limit=10&access=&page=1&page_size=20&order_published_at=DESC
        query_params = {
            "status": "published",
            "tags[]": keyword.replace(" ", "-"),
            "limit": "",
            "access": "",
            "page": page,
            "page_size": "20",
            "order_published_at": "DESC",
        }
        query_string = urlencode(query_params, doseq=True)
        url = f"{self.api_url}?{query_string}"
        return await self.fetch(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)

    def parse_article_links(self, response_text):
        try:
            response_json = json.loads(response_text)
        except Exception as e:
            logging.error(f"Error decoding JSON response: {e}")
            return None
        articles = response_json.get("data", [])
        filtered_hrefs = {
            f"{self.base_url}/{a['canonical_url']}"
            for a in articles
            if a["canonical_url"]
        }
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(
            link, headers={"User-Agent": "Mozilla/5.0"}, timeout=45
        )
        if not response_text:
            logging.warning(f"No response fetched for {link}")
            return
        soup = BeautifulSoup(response_text, "html.parser")
        try:
            ld_json_script = soup.find("script", type="application/ld+json")
            if not ld_json_script:
                logging.error("No application/ld+json script found in article page")
                return

            ld_json = json.loads(ld_json_script.string)

            # Tempo uses @graph; pick the node that contains article fields.
            article_node = ld_json
            if isinstance(ld_json, dict) and "@graph" in ld_json:
                graph = ld_json.get("@graph") or []
                if isinstance(graph, list):
                    article_node = next(
                        (
                            n
                            for n in graph
                            if isinstance(n, dict)
                            and (
                                n.get("@type") in {"NewsArticle", "Article"}
                                or n.get("headline")
                                or n.get("datePublished")
                            )
                        ),
                        {},
                    )

            title = (article_node.get("headline") or "").strip()
            publish_date_str = (article_node.get("datePublished") or "").strip()
            content = (article_node.get("articleBody") or "").strip()

            author_field = article_node.get("author", "")
            if isinstance(author_field, list):
                author = ", ".join(
                    [a.get("name", "") for a in author_field if a.get("name")]
                )
            elif isinstance(author_field, dict):
                author = author_field.get("name", "")
            else:
                author = ""

            main_entity = article_node.get("mainEntityOfPage", {})
            if isinstance(main_entity, dict):
                category_url = main_entity.get("@id", "")
                parts = category_url.split("/") if category_url else []
                category = parts[3] if len(parts) > 3 else ""
            else:
                category = ""

            # Fallback: if structured data doesn't include articleBody, parse HTML.
            if not content:
                body = (
                    soup.select_one('[data-testid="article-content"]')
                    or soup.select_one('div[itemprop="articleBody"]')
                    or soup.select_one("article")
                )
                if body:
                    content = body.get_text(separator=" ", strip=True)

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(f"Error parsing date for article {link}")
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
            logging.error(f"Error parsing article {link}: {e}", exc_info=True)
