"""Quick-range maths for the owner dashboard (Dubai business dates). No database needed."""

from datetime import UTC, date, datetime

import pytest

from app.core.exceptions import UnprocessableError
from app.services.dashboard_service import DashboardService, preset_bounds
from app.utils.time import dubai_today

TODAY = date(2026, 3, 15)


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("today", (date(2026, 3, 15), date(2026, 3, 15))),
        ("yesterday", (date(2026, 3, 14), date(2026, 3, 14))),
        ("last7", (date(2026, 3, 9), date(2026, 3, 15))),
        ("last30", (date(2026, 2, 14), date(2026, 3, 15))),
        ("this_month", (date(2026, 3, 1), date(2026, 3, 15))),
        ("last_month", (date(2026, 2, 1), date(2026, 2, 28))),
    ],
)
def test_preset_bounds(preset, expected) -> None:
    assert preset_bounds(preset, TODAY) == expected


def test_boundaries_across_year_and_first_of_month() -> None:
    assert preset_bounds("last_month", date(2026, 1, 1)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert preset_bounds("yesterday", date(2026, 3, 1)) == (date(2026, 2, 28), date(2026, 2, 28))
    assert preset_bounds("last_month", date(2024, 3, 31)) == (date(2024, 2, 1), date(2024, 2, 29))


def test_today_uses_dubai_not_utc() -> None:
    # 21:30 UTC on 14 Mar is already 15 Mar 01:30 in Dubai (UTC+4)
    assert dubai_today(datetime(2026, 3, 14, 21, 30, tzinfo=UTC)) == date(2026, 3, 15)
    assert dubai_today(datetime(2026, 3, 14, 19, 30, tzinfo=UTC)) == date(2026, 3, 14)


def test_custom_range_validation() -> None:
    check = DashboardService._check_range
    check(date(2026, 1, 1), date(2026, 3, 15), TODAY, 366)
    with pytest.raises(UnprocessableError):
        check(date(2026, 3, 2), date(2026, 3, 1), TODAY, 366)
    with pytest.raises(UnprocessableError):
        check(date(2026, 3, 1), date(2026, 3, 16), TODAY, 366)
    with pytest.raises(UnprocessableError):
        check(date(2025, 3, 1), date(2026, 3, 15), TODAY, 366)
