"""Step 13 order rules in one place: status workflow, payment arithmetic, mobile numbers, Dubai schedule times.
The same workflow is enforced again by the database (app.orders_before trigger)."""

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.core.calculations import ZERO, money
from app.core.exceptions import UnprocessableError
from app.utils.time import BUSINESS_TZ

STATUSES = (
    "New",
    "Scheduled",
    "Picked Up",
    "Processing",
    "Ready",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
)
FLOW = STATUSES[:-1]  # the forward chain
CLOSED = ("Delivered", "Cancelled")
CANCELLABLE = ("New", "Scheduled", "Picked Up", "Processing", "Ready")
SERVICE_TYPES = ("Standard", "Express")
PAYMENT_METHODS = ("Cash", "POS", "Bank Transfer", "Payment Link")
PAYMENT_STATUSES = ("Unpaid", "Partial", "Paid", "Refunded")


def next_status(current: str) -> str | None:
    """The single forward step from `current` (None when the order is finished or cancelled)."""
    if current in CLOSED or current not in FLOW:
        return None
    return FLOW[FLOW.index(current) + 1]


def final_payable(order_total: Decimal, discount: Decimal, service_fee: Decimal) -> Decimal:
    """Final Payable Amount = Order Total - Discount + Service Fee."""
    return money(order_total - discount + service_fee)


def outstanding(final: Decimal, collected: Decimal) -> Decimal:
    """Outstanding Balance = Final Payable Amount - Total Successful Payments."""
    return money(final - collected)


def payment_status(final: Decimal, collected: Decimal, refunded: bool = False) -> str:
    if refunded:
        return "Refunded"  # reserved: only a future, approved refund workflow may set it
    if collected <= ZERO:
        return "Unpaid"
    return "Paid" if collected >= final else "Partial"


_UAE_MOBILE = re.compile(r"^\+9715[0-9]{8}$")
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


def normalize_mobile(raw: str) -> str:
    """Return +E.164. UAE mobiles may be typed 05xxxxxxxx, 5xxxxxxxx, 9715xxxxxxxx or +9715xxxxxxxx; any other
    country needs the + prefix (or 00). Raises UnprocessableError for anything else."""
    s = re.sub(r"[\s\-().]", "", raw or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if re.fullmatch(r"05[0-9]{8}", s):
        s = "+971" + s[1:]
    elif re.fullmatch(r"5[0-9]{8}", s):
        s = "+971" + s
    elif re.fullmatch(r"9715[0-9]{8}", s):
        s = "+" + s
    if s.startswith("+971") and not _UAE_MOBILE.fullmatch(s):
        raise UnprocessableError(
            "Enter a valid UAE mobile number", fields={"mobile": ["Invalid UAE mobile number"]}
        )
    if not _E164.fullmatch(s):
        raise UnprocessableError(
            "Enter a valid mobile number",
            fields={"mobile": ["Use 05XXXXXXXX or +<country code><number>"]},
        )
    return s


def to_dubai_datetime(d: date, t: time) -> datetime:
    return datetime.combine(d, t.replace(second=0, microsecond=0), tzinfo=BUSINESS_TZ)


def day_bounds(d: date) -> tuple[datetime, datetime]:
    """[start, next start) of a Dubai calendar day, for index-friendly timestamp range queries."""
    start = datetime.combine(d, time.min, tzinfo=BUSINESS_TZ)
    return start, start + timedelta(days=1)
