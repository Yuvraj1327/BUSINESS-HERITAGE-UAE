"""Rental agreement and PDC cheque rules (docs/architecture/BUSINESS_LOGIC.md section 9), in ONE place.

* Agreement end date  = start + 12 calendar months - 1 day.
* Cheque amounts      = annual rent / n rounded to WHOLE dirhams (half up) for the first n-1 cheques; the LAST cheque
                        takes the remainder, so the total is always exactly the annual rent (decision R1).
* Cheque k date       = first cheque date + round(12 * k / n) calendar months, with k = 0 .. n-1 (so cheque 0 falls on
                        the first cheque date; decision R2). round() is half-up (n = 8: k = 1 -> 1.5 -> 2 months).
                        Every date is computed from the FIRST date (never chained), then clamped to the month end
                        (31 Jan + 1 month = 28/29 Feb).
* Cheque numbers      = first cheque number with its trailing digits incremented by one per cheque, keeping leading zeros.
All money is Decimal. Business dates are Dubai dates supplied by the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.core.calculations import add_calendar_months, money

MIN_CHEQUES, MAX_CHEQUES = 1, 12
DUE_SOON_DAYS = 30
DUE_URGENT_DAYS = 7
RENEWAL_NOTICE_DAYS = 90  # an agreement ending in 31..90 days is flagged "renewal approaching"


class ScheduleError(ValueError):
    """The inputs cannot produce a valid cheque schedule. `field` names the offending input."""

    def __init__(self, message: str, field: str = "annual_rent") -> None:
        super().__init__(message)
        self.field = field


def agreement_end_date(start: date) -> date:
    return add_calendar_months(start, 12) - timedelta(days=1)


def renewal_dates(old_end: date) -> tuple[date, date]:
    """New start = old end + 1 day; new end = new start + 12 months - 1 day."""
    start = old_end + timedelta(days=1)
    return start, agreement_end_date(start)


def month_offset(k: int, n: int) -> int:
    """round(12 * k / n), half up, in integer arithmetic (no float)."""
    return (24 * k + n) // (2 * n)


def split_amounts(rent: Decimal, n: int) -> list[Decimal]:
    if not MIN_CHEQUES <= n <= MAX_CHEQUES:
        raise ScheduleError("The number of cheques must be between 1 and 12", "cheque_count")
    rent = money(rent)
    if rent <= 0:
        raise ScheduleError("The annual rent must be greater than zero")
    base = (rent / n).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    last = rent - base * (n - 1)
    amounts = [money(base)] * (n - 1) + [money(last)]
    if any(a <= 0 for a in amounts):
        raise ScheduleError(f"The annual rent is too small to split into {n} cheques")
    assert sum(amounts, Decimal("0.00")) == rent
    return amounts


_TRAILING = re.compile(r"^(.*?)(\d+)$", re.DOTALL)


def parse_cheque_no(no: str) -> tuple[str, int, int] | None:
    """('CHQ-', 45, 4) for 'CHQ-0045'; None when the number has no trailing digits."""
    m = _TRAILING.match(no.strip())
    return None if m is None else (m.group(1), int(m.group(2)), len(m.group(2)))


def shift_cheque_no(no: str, steps: int, field: str = "first_cheque_no") -> str:
    p = parse_cheque_no(no)
    if p is None:
        raise ScheduleError(
            "The cheque number must end in digits (for example 100245) so later cheques can continue it",
            field,
        )
    prefix, num, width = p
    return f"{prefix}{str(num + steps).zfill(width)}"


def next_cheque_no(existing: list[str], first_no: str) -> str:
    """Numbering continues from the highest number on the same series (same prefix) as the agreement's first cheque."""
    series = parse_cheque_no(first_no)
    if series is None:
        raise ScheduleError("The cheque number must end in digits", "first_cheque_no")
    top = series[1]
    for no in existing:
        p = parse_cheque_no(no)
        if p is not None and p[0] == series[0]:
            top = max(top, p[1])
    return shift_cheque_no(first_no, top - series[1] + 1)


@dataclass(frozen=True)
class ChequeLine:
    seq: int  # k, 0-based
    cheque_no: str
    cheque_date: date
    amount: Decimal
    bank: str


def build_schedule(
    rent: Decimal, n: int, first_date: date, first_no: str, bank: Literal["ENBD", "ADCB"] | str
) -> list[ChequeLine]:
    amounts = split_amounts(rent, n)
    return [
        ChequeLine(
            seq=k,
            cheque_no=shift_cheque_no(first_no, k),
            cheque_date=add_calendar_months(first_date, month_offset(k, n)),
            amount=amounts[k],
            bank=bank,
        )
        for k in range(n)
    ]


AgreementStatus = Literal["Scheduled", "Active", "Expiring", "Expired", "Renewed", "Terminated"]


def agreement_status(stored: str, start: date, end: date, today: date) -> AgreementStatus:
    """Displayed status from the real dates (never typed)."""
    if stored == "Renewed":
        return "Renewed"
    if stored == "Terminated":
        return "Terminated"
    if end < today:
        return "Expired"
    if start > today:
        return "Scheduled"
    if end <= today + timedelta(days=DUE_SOON_DAYS):
        return "Expiring"
    return "Active"


def days_to(d: date, today: date) -> int:
    return (d - today).days
