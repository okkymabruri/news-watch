__version__ = "0.5.0"

# main api functions
from .api import list_scrapers as list_scrapers
from .api import quick_scrape as quick_scrape
from .api import scrape as scrape
from .api import scrape_to_dataframe as scrape_to_dataframe
from .api import scrape_to_file as scrape_to_file

__all__ = [
    "list_scrapers",
    "quick_scrape",
    "scrape",
    "scrape_to_dataframe",
    "scrape_to_file",
]
