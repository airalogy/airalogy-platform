from datetime import UTC, date, datetime

import pytest
from app.services.document_browse import date_bounds
from fastapi import HTTPException


def test_calendar_bounds_include_local_midnight_and_exclude_next_day():
    start, end = date_bounds(date(2026, 11, 7), date(2026, 11, 7), "Asia/Shanghai")
    assert start == datetime(2026, 11, 6, 16, tzinfo=UTC)
    assert end == datetime(2026, 11, 7, 16, tzinfo=UTC)


@pytest.mark.parametrize(
    ("day", "hours"), [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)]
)
def test_calendar_bounds_follow_daylight_saving_days(day, hours):
    start, end = date_bounds(day, day, "America/New_York")
    assert (end - start).total_seconds() == hours * 3600


@pytest.mark.parametrize(
    ("start", "end", "zone"),
    [
        (date(2026, 11, 8), date(2026, 11, 7), "UTC"),
        (None, None, "Unknown/Nowhere"),
        (None, date.max, "UTC"),
    ],
)
def test_invalid_calendar_filters_are_actionable(start, end, zone):
    with pytest.raises(HTTPException) as error:
        date_bounds(start, end, zone)
    assert error.value.status_code == 422
