from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ScraperStatus(Enum):
    """Enumeration for scraper operation status"""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class Article:
    """Structured article data model"""

    title: str
    publish_date: datetime
    author: Optional[str]
    content: str
    keyword: str
    category: Optional[str]
    source: str
    link: str
    scrape_timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility"""
        return {
            "title": self.title,
            "publish_date": self.publish_date.strftime("%Y-%m-%d %H:%M:%S"),
            "author": self.author,
            "content": self.content,
            "keyword": self.keyword,
            "category": self.category,
            "source": self.source,
            "link": self.link,
            "scrape_timestamp": self.scrape_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }


@dataclass
class ScrapeResult:
    """Container for scraping operation results"""

    articles: List[Article]
    status: ScraperStatus
    total_scraped: int
    failed_scrapers: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
