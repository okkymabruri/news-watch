__version__ = "0.8.5"

# main api functions
from .api import latest as latest
from .api import latest_to_dataframe as latest_to_dataframe
from .api import latest_to_file as latest_to_file
from .api import list_scrapers as list_scrapers
from .api import quick_scrape as quick_scrape
from .api import scrape as scrape
from .api import scrape_to_dataframe as scrape_to_dataframe
from .api import scrape_to_file as scrape_to_file

# registry access
from .registry import SCRAPERS as SCRAPERS
from .registry import get_scraper_by_slug as get_scraper_by_slug
from .registry import get_stable_slugs as get_stable_slugs
from .registry import get_stable_scrapers as get_stable_scrapers

__all__ = [
    "latest",
    "latest_to_dataframe",
    "latest_to_file",
    "list_scrapers",
    "quick_scrape",
    "scrape",
    "scrape_to_dataframe",
    "scrape_to_file",
    "SCRAPERS",
    "get_scraper_by_slug",
    "get_stable_scrapers",
    "get_stable_slugs",
]
