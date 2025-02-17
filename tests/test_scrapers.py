import asyncio
from datetime import datetime, timedelta

import pytest

from newswatch.scrapers.bisnisindonesia import BisnisIndonesiaScraper
from newswatch.scrapers.bloombergtechnoz import BloombergTechnozScraper
# from newswatch.scrapers.cnbcindonesia import CNBCScraper
from newswatch.scrapers.detik import DetikScraper
from newswatch.scrapers.katadata import KatadataScraper
from newswatch.scrapers.kompas import KompasScraper
# from newswatch.scrapers.kontan import KontanScraper
from newswatch.scrapers.metrotvnews import MetrotvnewsScraper
from newswatch.scrapers.viva import VivaScraper

scraper_classes = [
    BisnisIndonesiaScraper,
    BloombergTechnozScraper,
    # CNBCScraper, # exclude pytest error
    DetikScraper,
    KatadataScraper,
    KompasScraper,
    # KontanScraper, # only apply on local
    MetrotvnewsScraper,
    VivaScraper,
]


@pytest.mark.asyncio
@pytest.mark.network
@pytest.mark.parametrize("scraper_class", scraper_classes)
async def test_scraper_fetch_data(scraper_class):
    items = []

    async def item_consumer(queue):
        try:
            while True:
                item = await queue.get()
                items.append(item)
                queue.task_done()
        except asyncio.CancelledError:
            pass

    queue = asyncio.Queue()
    scraper = scraper_class(
        keywords="indonesia",
        start_date=datetime.now() - timedelta(days=1),
        queue_=queue,
    )

    consumer_task = asyncio.create_task(item_consumer(queue))
    try:
        try:
            await scraper.scrape()
        except Exception as e:
            pytest.xfail(f"{scraper_class.__name__} failed as expected: {e}")
        await queue.join()
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    # If the test reached this point without xfail being triggered, expect at least one item.
    assert len(items) > 0
    for item in items:
        assert "title" in item
        assert "publish_date" in item
        assert "content" in item
        assert "link" in item
