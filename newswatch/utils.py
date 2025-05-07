import asyncio
import logging

import aiohttp


class AsyncScraper:
    def __init__(self, concurrency=12, max_retries=3):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.session = None
        self.max_retries = max_retries

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_connect=10, sock_read=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.session:
            await self.session.close()

    async def fetch(
        self, url, method="GET", data=None, headers=None, retries=0, timeout=30
    ):
        async with self.semaphore:
            try:
                # Create request-specific timeout
                request_timeout = aiohttp.ClientTimeout(total=timeout)
                
                if method == "GET":
                    async with self.session.get(
                        url, headers=headers, timeout=request_timeout
                    ) as response:
                        response.raise_for_status()
                        return await response.text()
                elif method == "POST":
                    async with self.session.post(
                        url, data=data, headers=headers, timeout=request_timeout
                    ) as response:
                        response.raise_for_status()
                        return await response.text()
            except aiohttp.ClientResponseError as e:
                status = getattr(e, 'status', None)
                if status == 429 or status in (500, 502, 503, 504):  # Rate limit or server error
                    if retries < self.max_retries:
                        wait_time = 2 ** retries  # Exponential backoff
                        logging.warning(f"Received status {status}, retry {retries+1}/{self.max_retries} for {url} in {wait_time}s")
                        await asyncio.sleep(wait_time)
                        return await self.fetch(
                            url, method, data, headers, retries + 1, timeout
                        )
                logging.error(f"Error {status} fetching {url}: {e}")
                return None
            except aiohttp.ClientError as e:
                if retries < self.max_retries:
                    wait_time = 1 * (retries + 1)
                    logging.warning(f"Retry {retries+1}/{self.max_retries} for {url} in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    return await self.fetch(
                        url, method, data, headers, retries + 1, timeout
                    )
                else:
                    logging.error(f"Error fetching {url}: {e}")
                    return None
            except asyncio.TimeoutError:
                if retries < self.max_retries:
                    wait_time = 1 * (retries + 1)
                    logging.warning(f"Timeout retry {retries+1}/{self.max_retries} for {url} in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    return await self.fetch(
                        url, method, data, headers, retries + 1, timeout + 5
                    )
                logging.error(f"Timeout fetching {url}")
                return None
            except Exception as e:
                logging.error(f"Unexpected error fetching {url}: {e}")
                return None

    async def run(self, tasks):
        try:
            return await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logging.error(f"Error running tasks: {e}")
            return None
