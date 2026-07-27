"""One clock for publish timestamps.

Publishers report in whatever zone they use: ``+07:00`` from Indonesian
sources, ``-04:00`` from US ones, ``Z`` from wire feeds. Queue payloads,
``--start_date`` and ``--time_range`` are all naive datetimes, so every source
has to agree on what a naive value *means* -- otherwise a single output file
carries two clocks and the date filters compare across them.

That reference zone is ``Asia/Jakarta`` (override: ``NEWSWATCH_TIMEZONE``).
It is the zone the large majority of registered sources already publish in, so
converting into it leaves their timestamps unchanged while giving
offset-bearing sources a correct place to land.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from . import config


def project_timezone():
    """The reference zone as a ZoneInfo."""
    return ZoneInfo(config.get_timezone())


def to_project_naive(value, assume_tz=None):
    """Convert to the reference zone, then drop tzinfo.

    Aware input is converted -- the offset is honored, not discarded. Naive
    input is returned unchanged unless ``assume_tz`` states which zone it was
    already in, so the common case is a no-op rather than a silent
    reinterpretation. Non-datetime input passes through so callers can apply
    this before their own type checks.
    """
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        if assume_tz is None:
            return value
        value = value.replace(tzinfo=assume_tz)
    return value.astimezone(project_timezone()).replace(tzinfo=None)
