from __future__ import annotations

from datetime import timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


FIXED_TIMEZONE_FALLBACKS: dict[str, tzinfo] = {
    "UTC": timezone.utc,
    "Asia/Tokyo": timezone(timedelta(hours=9), "Asia/Tokyo"),
    "Asia/Shanghai": timezone(timedelta(hours=8), "Asia/Shanghai"),
}


def get_timezone(timezone_name: str) -> tzinfo:
    name = (timezone_name or "Asia/Tokyo").strip() or "Asia/Tokyo"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        fallback = FIXED_TIMEZONE_FALLBACKS.get(name)
        if fallback is not None:
            return fallback
        raise
