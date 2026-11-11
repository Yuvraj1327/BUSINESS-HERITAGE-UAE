"""Step 10 pure-calculation tests: agreement dates, cheque amounts/dates/numbers, status. No database needed."""

from datetime import date
from decimal import Decimal

import pytest

from app.core import rentals as r


def test_end_date_is_start_plus_12_months_minus_one_day() -> None:
    assert r.agreement_end_date(date(2026, 3, 1)) == date(2027, 2, 28)
    assert r.agreement_end_date(date(2026, 1, 15)) == date(2027, 1, 14)
    assert r.agreement_end_date(date(2028, 2, 29)) == date(2029, 2, 27)  # leap start, non-leap end


def test_renewal_dates_follow_the_old_end() -> None:
    start, end = r.renewal_dates(date(2027, 2, 28))
    assert (start, end) == (date(2027, 3, 1), date(2028, 2, 29))


@pytest.mark.parametrize(
    ("rent", "n", "regular", "last"),
    [
        ("100000", 12, "8333.00", "8337.00"),
        ("120000", 12, "10000.00", "10000.00"),
        ("90000", 4, "22500.00", "22500.00"),
        ("100000", 3, "33333.00", "33334.00"),
        ("50000", 1, "50000.00", "50000.00"),
    ],
)
def test_split_amounts_total_equals_rent(rent: str, n: int, regular: str, last: str) -> None:
    amounts = r.split_amounts(Decimal(rent), n)
    assert len(amounts) == n
    assert sum(amounts) == Decimal(rent)
    assert all(a == Decimal(regular) for a in amounts[:-1])
    assert amounts[-1] == Decimal(last)


def test_split_amounts_handles_fils() -> None:
    amounts = r.split_amounts(Decimal("100000.55"), 3)
    assert sum(amounts) == Decimal("100000.55")


def test_split_amounts_rejects_unsplittable_rent() -> None:
    with pytest.raises(r.ScheduleError):
        r.split_amounts(Decimal("5"), 12)


@pytest.mark.parametrize(
    ("n", "offsets"),
    [
        (1, [0]),
        (2, [0, 6]),
        (4, [0, 3, 6, 9]),
        (6, [0, 2, 4, 6, 8, 10]),
        (8, [0, 2, 3, 5, 6, 8, 9, 11]),
        (12, list(range(12))),
    ],
)
def test_month_offset_is_zero_based_round_12k_over_n(n: int, offsets: list[int]) -> None:
    assert [r.month_offset(k, n) for k in range(n)] == offsets


def test_schedule_dates_come_from_the_first_date_and_clamp_to_month_end() -> None:
    lines = r.build_schedule(Decimal("120000"), 12, date(2026, 1, 31), "000100", "ENBD")
    assert [ln.cheque_date for ln in lines][:4] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),  # not chained from Feb 28
        date(2026, 4, 30),
    ]
    assert lines[0].seq == 0 and lines[-1].cheque_no == "000111"
    assert sum(ln.amount for ln in lines) == Decimal("120000")


def test_cheque_numbers_keep_leading_zeros_and_prefix() -> None:
    assert r.shift_cheque_no("000099", 1) == "000100"
    assert r.shift_cheque_no("AB0009", 2) == "AB0011"
    with pytest.raises(r.ScheduleError):
        r.shift_cheque_no("NODIGITS", 1)


def test_renewal_numbering_continues_after_the_highest_number() -> None:
    assert r.next_cheque_no(["000099", "000110", "X5"], "000099") == "000111"


@pytest.mark.parametrize(
    ("stored", "start", "end", "expected"),
    [
        ("Active", date(2026, 1, 1), date(2026, 12, 31), "Active"),
        ("Active", date(2026, 1, 1), date(2026, 11, 30), "Expiring"),
        ("Active", date(2026, 1, 1), date(2026, 11, 9), "Expired"),
        ("Active", date(2026, 12, 1), date(2027, 11, 30), "Scheduled"),
        ("Renewed", date(2025, 1, 1), date(2025, 12, 31), "Renewed"),
        ("Terminated", date(2026, 1, 1), date(2026, 12, 31), "Terminated"),
    ],
)
def test_agreement_status_from_dates(stored: str, start: date, end: date, expected: str) -> None:
    assert r.agreement_status(stored, start, end, date(2026, 11, 10)) == expected
