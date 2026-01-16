import logging
from argparse import Namespace

import pytest

from newswatch.main import main


@pytest.mark.asyncio
async def test_main_no_scrapers(caplog):
    caplog.set_level(logging.ERROR)
    args = Namespace(
        keywords="test", start_date="2023-10-01", scrapers="invalid_scraper", verbose=0
    )
    await main(args)
    assert "no valid scrapers selected. exiting." in caplog.text
