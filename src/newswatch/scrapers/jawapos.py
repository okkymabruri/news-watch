import json
import logging

from bs4 import BeautifulSoup

from .basescraper import BaseScraper


class JawaposScraper(BaseScraper):
    def __init__(self, keywords, concurrency=5, start_date=None, queue_=None):
        super().__init__(keywords, concurrency, queue_)
        self.base_url = "https://www.jawapos.com"
        self.start_date = start_date
        self.continue_scraping = True

    async def build_search_url(self, keyword, page):
        url = f"https://www.jawapos.com/search?q={keyword.replace(' ', '+')}&sort=latest&page={page}"
        return await self.fetch(url)

    def parse_article_links(self, response_text):
        soup = BeautifulSoup(response_text, "html.parser")

        # Next.js __NEXT_DATA__ contains initialArticles
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                data = json.loads(script.string)
                articles = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("initialArticles", [])
                )
                if articles:
                    filtered_hrefs = set()
                    for a in articles:
                        slug = a.get("slug", "")
                        article_id = a.get("article_id", "")
                        category = a.get("category", {})
                        cat_slug = category.get("slug", "news") if isinstance(category, dict) else "news"
                        if slug and article_id:
                            filtered_hrefs.add(f"{self.base_url}/{cat_slug}/{article_id}/{slug}")
                    return filtered_hrefs or None
            except (json.JSONDecodeError, AttributeError):
                pass

        # Fallback — legacy CSS selectors
        articles = soup.select("a.latest__link[href]")
        if not articles:
            return None

        filtered_hrefs = {f"{a.get('href')}" for a in articles if a.get("href")}
        return filtered_hrefs

    async def get_article(self, link, keyword):
        response_text = await self.fetch(link)
        if not response_text:
            logging.warning(f"No response for {link}")
            return

        soup = BeautifulSoup(response_text, "html.parser")

        # Extract from __NEXT_DATA__ (Next.js SSR)
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                data = json.loads(script.string)
                article = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("article", {})
                )
                if article:
                    await self._parse_article_from_data(article, link, keyword)
                    return
            except (json.JSONDecodeError, AttributeError):
                pass

        # Fallback — legacy HTML selectors
        try:
            category_el = soup.select_one(".breadcrumb__wrap")
            category = category_el.get_text(strip=True) if category_el else ""
            title_el = soup.select_one("h1.read__title")
            title = title_el.get_text() if title_el else ""
            if not title:
                og = soup.select_one("meta[property='og:title']")
                title = og.get("content", "") if og and og.get("content") else ""
            if not title:
                return

            date_el = soup.select_one(".read__info__date")
            publish_date_str = (
                date_el.get_text(strip=True).replace("- ", "").replace("| ", "")
                if date_el else ""
            )
            author_el = soup.select_one(".read__info__author")
            author = author_el.get_text(strip=True) if author_el else "Unknown"

            content_div = soup.select_one(".read__content.clearfix")
            if not content_div:
                content_div = soup.select_one("article")
            if not content_div:
                return

            for tag in content_div.find_all(["strong"]):
                if tag and any(
                    cls.startswith("read__others") for cls in tag.get("class", [])
                ):
                    tag.extract()

            content = content_div.get_text(separator=" ", strip=True)

            publish_date = self.parse_date(publish_date_str)
            if not publish_date:
                logging.error(
                    f"JawaPos date parse failed | url: {link} | date: {repr(publish_date_str[:50])}"
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
                "category": category,
                "source": self.base_url.split("www.")[1],
                "link": link,
            }
            await self.queue_.put(item)
        except Exception as e:
            logging.error(f"Error parsing article {link}: {e}", exc_info=True)

    async def _parse_article_from_data(self, article, link, keyword):
        """Parse article from Next.js __NEXT_DATA__ payload."""
        title = (article.get("title") or "").strip()
        if not title:
            return

        content_html = article.get("content", "")
        if not content_html:
            return
        content_soup = BeautifulSoup(content_html, "html.parser")
        content = content_soup.get_text(separator=" ", strip=True)
        if not content:
            return

        published_at = article.get("published_at", "")
        publish_date = self.parse_date(published_at)
        if not publish_date:
            logging.error(
                f"JawaPos date parse failed | url: {link} | date: {repr(published_at[:50])}"
            )
            return
        if self.start_date and publish_date < self.start_date:
            self.continue_scraping = False
            return

        authors = article.get("authors", [])
        author = ", ".join(
            [a.get("name", "") for a in authors if isinstance(a, dict) and a.get("name")]
        ) or "Unknown"

        category = ""
        cat = article.get("category", {})
        if isinstance(cat, dict):
            category = cat.get("name", "")

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
