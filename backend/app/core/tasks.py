"""Step 11 pure task rules (Dubai business dates are passed in by the caller)."""

from datetime import date

STATUSES = ("To Do", "In Progress", "Done")
DUE_SOON_DAYS = 7


def timing_of(status: str, due: date | None, today: date) -> tuple[str, int | None]:
    """completed | no_due_date | overdue | due_today | upcoming, and days until due (negative = overdue).

    Overdue = the due date has passed AND the status is not Done. A Done task is never overdue."""
    if status == "Done":
        return "completed", None if due is None else (due - today).days
    if due is None:
        return "no_due_date", None
    days = (due - today).days
    if days < 0:
        return "overdue", days
    if days == 0:
        return "due_today", 0
    return "upcoming", days
