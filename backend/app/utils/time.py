from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("Asia/Dubai")


def dubai_today(now: datetime | None = None) -> date:
    """Today's business date in Dubai (matches app.dubai_today() in the database)."""
    return (now or datetime.now(BUSINESS_TZ)).astimezone(BUSINESS_TZ).date()
