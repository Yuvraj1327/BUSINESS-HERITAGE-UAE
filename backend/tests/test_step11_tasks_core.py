from datetime import date, timedelta

import pytest

from app.core.tasks import timing_of

T = date(2026, 11, 10)


@pytest.mark.parametrize(
    ("status", "due", "expected"),
    [
        ("To Do", T - timedelta(days=1), ("overdue", -1)),
        ("In Progress", T - timedelta(days=30), ("overdue", -30)),
        ("To Do", T, ("due_today", 0)),
        ("To Do", T + timedelta(days=1), ("upcoming", 1)),
        ("To Do", None, ("no_due_date", None)),
        ("Done", T - timedelta(days=5), ("completed", -5)),  # Done is never overdue
        ("Done", None, ("completed", None)),
    ],
)
def test_timing(status: str, due: date | None, expected: tuple[str, int | None]) -> None:
    assert timing_of(status, due, T) == expected
