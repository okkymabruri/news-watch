import asyncio
import logging

import aiohttp


class AsyncScraper:
    def __init__(self, concurrency=12, max_retries=3):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.session = None
        self.max_retries = max_retries

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.session:
            await self.session.close()

    async def fetch(
        self, url, method="GET", data=None, headers=None, retries=0, timeout=30
    ):
        async with self.semaphore:
            try:
                if method == "GET":
                    async with self.session.get(
                        url, headers=headers, timeout=timeout
                    ) as response:
                        response.raise_for_status()
                        return await response.text()
                elif method == "POST":
                    async with self.session.post(
                        url, data=data, headers=headers, timeout=timeout
                    ) as response:
                        response.raise_for_status()
                        return await response.text()
            except aiohttp.ClientError as e:
                if retries < self.max_retries:
                    logging.warning(f"Retry {retries+1}/{self.max_retries} for {url}")
                    await asyncio.sleep(1 * retries)
                    return await self.fetch(
                        url, method, data, headers, retries + 1, timeout
                    )
                else:
                    logging.error(f"Error fetching {url}: {e}")
                    return None
            except asyncio.TimeoutError:
                logging.error(f"Timeout fetching {url}")
                return None
            except Exception as e:
                logging.error(f"Unexpected error fetching {url}: {e}")
                return None

    async def run(self, tasks):
        return await asyncio.gather(*tasks)
