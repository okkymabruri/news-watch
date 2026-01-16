import asyncio
import logging
import platform

import aiohttp


async def _playwright_get(url: str, headers: dict | None, timeout: int) -> str | None:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(extra_http_headers=headers or {})
                try:
                    # Try fast request API first (good for JSON endpoints)
                    resp = await context.request.get(url, timeout=timeout * 1000)
                    if resp.ok:
                        text = await resp.text()
                        if text and not _looks_blocked(text):
                            return text

                    # Fall back to real navigation (better for WAF/cookie challenges)
                    page = await context.new_page()
                    try:
                        r = await page.goto(
                            url,
                            timeout=timeout * 1000,
                            wait_until="domcontentloaded",
                        )
                        if r and r.ok:
                            content = await page.content()
                            if content and not _looks_blocked(content):
                                return content
                        return None
                    finally:
                        await page.close()
                finally:
                    await context.close()
            finally:
                await browser.close()
    except Exception as e:
        logging.debug("playwright fallback failed for %s: %s", url, e)
        return None


def _looks_blocked(text: str) -> bool:
    head = text[:4000].lower()
    if "<html" not in head and "<!doctype" not in head:
        return False
    block_markers = (
        "access denied",
        "forbidden",
        "captcha",
        "cloudflare",
        "attention required",
        "verify you are human",
        "checking your browser",
        "incapsula",
        "sucuri",
        "akamai",
    )
    return any(m in head for m in block_markers)


class AsyncScraper:
    def __init__(self, concurrency=12, max_retries=3):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.session = None
        self.max_retries = max_retries

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(
            total=60, connect=10, sock_connect=10, sock_read=30
        )
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
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
                        text = await response.text()

                        if (
                            platform.system().lower() == "linux"
                            and text
                            and _looks_blocked(text)
                        ):
                            merged_headers = dict(self.session.headers)
                            if headers:
                                merged_headers.update(headers)
                            pw_text = await _playwright_get(
                                url, merged_headers, timeout
                            )
                            if pw_text:
                                return pw_text

                        return text
                elif method == "POST":
                    async with self.session.post(
                        url, data=data, headers=headers, timeout=request_timeout
                    ) as response:
                        response.raise_for_status()
                        return await response.text()
            except aiohttp.ClientResponseError as e:
                status = getattr(e, "status", None)
                if (
                    method == "GET"
                    and platform.system().lower() == "linux"
                    and status in (401, 403, 406, 418)
                ):
                    merged_headers = dict(self.session.headers)
                    if headers:
                        merged_headers.update(headers)
                    text = await _playwright_get(url, merged_headers, timeout)
                    if text:
                        return text
                if status == 429 or status in (
                    500,
                    502,
                    503,
                    504,
                ):  # Rate limit or server error
                    if retries < self.max_retries:
                        wait_time = 2**retries  # Exponential backoff
                        logging.warning(
                            f"Received status {status}, retry {retries + 1}/{self.max_retries} for {url} in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        return await self.fetch(
                            url, method, data, headers, retries + 1, timeout
                        )
                logging.error(f"Error {status} fetching {url}: {e}")
                return None
            except aiohttp.ClientError as e:
                if method == "GET" and platform.system().lower() == "linux":
                    merged_headers = dict(self.session.headers)
                    if headers:
                        merged_headers.update(headers)
                    text = await _playwright_get(url, merged_headers, timeout)
                    if text:
                        return text
                if retries < self.max_retries:
                    wait_time = 1 * (retries + 1)
                    logging.warning(
                        f"Retry {retries + 1}/{self.max_retries} for {url} in {wait_time}s"
                    )
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
                    logging.warning(
                        f"Timeout retry {retries + 1}/{self.max_retries} for {url} in {wait_time}s"
                    )
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
