"""Business calculations (docs/architecture/BUSINESS_LOGIC.md §2-3), in ONE place.

Every report row, aggregate, dashboard KPI and Branch & Date View figure is produced by these functions, and the
frontend only displays what the API returns. Money is `Decimal`; results are rounded to fils (2 places).
Database sums of numeric(14,2) are exact, so no floating-point arithmetic is involved anywhere.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

ZERO = Decimal("0.00")
_CENT = Decimal("0.01")

CheckLabel = Literal["Matches", "Diff"]


def money(value: Decimal | int | str | None) -> Decimal:
    """Normalise to a 2-place Decimal (None -> 0.00)."""
    if value is None:
        return ZERO
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def total_received(
    cash: Decimal, pos: Decimal, bank_transfer: Decimal, link_payment: Decimal
) -> Decimal:
    """Total Collections = cash + POS + bank transfers + payment links."""
    return money(cash + pos + bank_transfer + link_payment)


def difference(total_sales: Decimal, received: Decimal) -> Decimal:
    """Reconciliation difference = total sales - total collections (0 = everything received)."""
    return money(total_sales - received)


def not_yet_received(total_sales: Decimal, received: Decimal) -> Decimal:
    """Not yet received = total sales - total collections (the same figure as the difference, by definition)."""
    return difference(total_sales, received)


def check_label(diff: Decimal) -> CheckLabel:
    return "Matches" if money(diff) == ZERO else "Diff"


def shop_expenses_excl_savings(shop_expenses: Decimal, shop_savings: Decimal) -> Decimal:
    """Shop expenses (excluding savings) = shop expenses - shop savings."""
    return money(shop_expenses - shop_savings)


def head_office_excl_savings(head_office_total: Decimal, head_office_savings: Decimal) -> Decimal:
    """Head office expenses (excluding savings) = total - items marked as savings."""
    return money(head_office_total - head_office_savings)


def total_savings(shop_savings: Decimal, head_office_savings: Decimal) -> Decimal:
    """Savings for a period = shop savings + head office expenses marked as savings."""
    return money(shop_savings + head_office_savings)


def sales_minus_expenses(
    total_sales: Decimal, shop_excl_savings: Decimal, head_office_excl: Decimal
) -> Decimal:
    """Sales minus expenses = sales - shop expenses (excl. savings) - head office expenses (excl. savings)."""
    return money(total_sales - shop_excl_savings - head_office_excl)


def supplier_outstanding(opening: Decimal, new_dues: Decimal, payments: Decimal) -> Decimal:
    """Outstanding = opening outstanding + new dues - recorded payments (never an overwritten figure)."""
    return money(opening + new_dues - payments)


def closing_balance(opening: Decimal, incoming: Decimal, outgoing: Decimal) -> Decimal:
    """Closing = opening + incoming - outgoing (outgoing given as a positive amount)."""
    return money(opening + incoming - outgoing)


# ------------------------------------------------------------------------------------------------ Step 9: dates
LEAVE_LIMIT_MONTHS = 6
LEAVE_APPROACH_DAYS = 30  # "close to the limit" = limit date within 30 days (BUSINESS_LOGIC §7)
VISA_RED_DAYS, VISA_AMBER_DAYS = 30, 90
PASSPORT_RED_DAYS, PASSPORT_AMBER_DAYS = 30, 180
LICENSE_RED_DAYS, LICENSE_AMBER_DAYS = (
    30,
    90,
)  # licence colours are not approved; mirrors the visa thresholds (D-S9-5)
LICENSE_FEES_DUE_DAYS = 90  # approved: renewal fees due = licences expiring within 90 days

ExpiryStatus = Literal["expired", "urgent", "upcoming", "normal", "not_recorded"]
LeaveState = Literal[
    "not_on_leave", "on_leave", "approaching_limit", "limit_reached", "visa_cancelled"
]


def add_calendar_months(d: date, months: int) -> date:
    """d + N calendar months. If the target month is shorter the date is clamped to its last day
    (31 Aug + 6 months = 28/29 Feb), matching PostgreSQL's `date + interval 'N months'`."""
    index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_one_year(d: date) -> date:
    """Licence renewal: expiry + 1 year (29 Feb -> 28 Feb of the next year)."""
    return add_calendar_months(d, 12)


def leave_limit_date(leave_start: date) -> date:
    """Six CALENDAR months after the leave start (never 180 days). The visa shows as cancelled AFTER this date."""
    return add_calendar_months(leave_start, LEAVE_LIMIT_MONTHS)


@dataclass(frozen=True)
class LeaveInfo:
    leave_start: date
    limit_date: date
    days_on_leave: int
    days_remaining: int  # negative once the limit has passed
    state: LeaveState


def leave_info(leave_start: date, today: date, visa_cancelled: bool = False) -> LeaveInfo:
    """Leave facts for one employee on one date.

    remaining > 30 -> on_leave; 1..30 -> approaching_limit; 0 (the limit date itself, the last allowed day)
    -> limit_reached; < 0 or a permanent cancellation -> visa_cancelled.
    """
    limit = leave_limit_date(leave_start)
    remaining = (limit - today).days
    if visa_cancelled or remaining < 0:
        state: LeaveState = "visa_cancelled"
    elif remaining == 0:
        state = "limit_reached"
    elif remaining <= LEAVE_APPROACH_DAYS:
        state = "approaching_limit"
    else:
        state = "on_leave"
    return LeaveInfo(leave_start, limit, (today - leave_start).days, remaining, state)


def returns_after_limit(leave_start: date, return_date: date) -> bool:
    """Returning on or before the limit date keeps the visa; returning after it makes the cancellation permanent."""
    return return_date > leave_limit_date(leave_start)


def expiry_status(
    expiry: date | None, today: date, amber_days: int, red_days: int = 30
) -> tuple[ExpiryStatus, int | None]:
    """Status from the ACTUAL date (never a typed label). Red = expired or within `red_days`; amber = within
    `amber_days`; otherwise normal. Returns (status, days_remaining); days are negative when expired."""
    if expiry is None:
        return "not_recorded", None
    days = (expiry - today).days
    if days < 0:
        return "expired", days
    if days <= red_days:
        return "urgent", days
    if days <= amber_days:
        return "upcoming", days
    return "normal", days


def visa_status(expiry: date | None, today: date) -> tuple[ExpiryStatus, int | None]:
    return expiry_status(expiry, today, VISA_AMBER_DAYS, VISA_RED_DAYS)


def passport_status(expiry: date | None, today: date) -> tuple[ExpiryStatus, int | None]:
    return expiry_status(expiry, today, PASSPORT_AMBER_DAYS, PASSPORT_RED_DAYS)


def license_status(expiry: date, today: date) -> tuple[ExpiryStatus, int]:
    status, days = expiry_status(expiry, today, LICENSE_AMBER_DAYS, LICENSE_RED_DAYS)
    return status, int(days or 0)
