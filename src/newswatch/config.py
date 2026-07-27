"""Runtime config read from env. Single source for proxy/UA/retry overrides."""

import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEZONE = "Asia/Jakarta"


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

def get_timezone():
    """IANA zone that naive publish timestamps are expressed in.

    Reads ``NEWSWATCH_TIMEZONE``. Unset, empty, or not a known zone →
    DEFAULT_TIMEZONE. Every source converts into this zone, so changing it
    changes what a naive ``publish_date`` and a ``--time_range`` boundary mean.
    """
    value = os.environ.get("NEWSWATCH_TIMEZONE")
    if not value:
        return DEFAULT_TIMEZONE
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_TIMEZONE
    return value


def get_health_history_path() -> str | None:
    """Path for append-only JSONL health history, or None.

    Reads ``NEWSWATCH_HEALTH_HISTORY``. Empty string is treated as unset.
    Callers should use the result to decide whether to enable history
    appending (None → skip persistence).
    """
    value = os.environ.get("NEWSWATCH_HEALTH_HISTORY")
    if not value:
        return None
    return value
