"""Configurable freshness limits for public program evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping

from .schemas import Source


DEFAULT_MAX_AGE_DAYS = {
    "offerings.application_window.closes": 1,
    "requirements": 7,
    "costs": 7,
    "funding": 7,
    "curriculum": 30,
    "program.duration": 30,
    "program.credits": 30,
    "program": 90,
}


def stale_after(source: Source, field: str, *, max_age_days: Mapping[str, int] = DEFAULT_MAX_AGE_DAYS) -> datetime:
    """Return expiry for a field; specific keys take precedence over prefixes."""
    matching = [key for key in max_age_days if field == key or field.startswith(key + ".")]
    days = max_age_days[max(matching, key=len)] if matching else 7
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("freshness days must be a non-negative integer")
    fetched_at = datetime.fromisoformat(source.fetched_at.replace("Z", "+00:00"))
    return fetched_at + timedelta(days=days)


def is_stale(
    source: Source,
    field: str,
    *,
    now: datetime | None = None,
    max_age_days: Mapping[str, int] = DEFAULT_MAX_AGE_DAYS,
) -> bool:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    return current > stale_after(source, field, max_age_days=max_age_days)
