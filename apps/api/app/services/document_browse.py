"""Calendar boundaries for the same occurrence times used by Research Log."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException


def date_bounds(date_from: date | None, date_to: date | None, time_zone: str):
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Unknown calendar timezone") from None
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Start date must not be after end date")
    if date_to == date.max:
        raise HTTPException(422, "End date is outside the supported range")
    # Use local calendar midnights, not a fixed 24 hours: DST days differ in length.
    start = (
        datetime.combine(date_from, time.min, zone).astimezone(UTC)
        if date_from
        else None
    )
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, zone).astimezone(UTC)
        if date_to
        else None
    )
    return start, end
