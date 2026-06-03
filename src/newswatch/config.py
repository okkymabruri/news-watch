"""Runtime config read from env. Single source for proxy/UA/retry overrides."""

import os

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_MAX_RETRIES = 3


def get_proxy():
    """Proxy URL or None. NEWSWATCH_PROXY wins, then HTTPS_PROXY/HTTP_PROXY."""
    for key in ("NEWSWATCH_PROXY", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def get_user_agent():
    """UA override or default."""
    return os.environ.get("NEWSWATCH_USER_AGENT") or DEFAULT_USER_AGENT


def get_max_retries():
    """Retry count override or default.

    Validates the env value:
    - Unset, empty, non-integer, or negative → DEFAULT_MAX_RETRIES.
    - Zero or positive integer → that value (0 disables retries).
    """
    value = os.environ.get("NEWSWATCH_MAX_RETRIES")
    if not value:
        return DEFAULT_MAX_RETRIES
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_RETRIES
    if parsed < 0:
        return DEFAULT_MAX_RETRIES
    return parsed
