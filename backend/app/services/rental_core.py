"""Shared Step 10 plumbing: error mapping, schedule validation, row -> API model conversion.
Built on FinanceCore so cheque clearing uses the SAME ledger, locks, tracking-start and balance rules as Step 8."""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import rentals as rules
from app.core.calculations import money
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.repositories.rental_repository import RentalRepository
from app.schemas.rentals import ChequeLineIn
from app.services.finance_core import FinanceCore, _message, constraint, sqlstate


def need_reason(reason: str | None, what: str) -> str:
    if not reason or len(reason.strip()) < 3:
        raise UnprocessableError(
            f"A reason (at least 3 characters) is required {what}",
            code="reason_required",
            fields={"reason": [f"Enter a reason {what}"]},
        )
    return reason.strip()


class RentalCore(FinanceCore):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.rent = RentalRepository(session)

    # ---- errors ------------------------------------------------------------------------------------------
    def translate(self, exc: DBAPIError) -> Exception:
        state, name = sqlstate(exc), constraint(exc)
        if state == "23505":
            if name == "pdc_bank_no_uq":
                return ConflictError(
                    "A cheque with this number already exists on this bank",
                    code="duplicate_cheque",
                    fields={"cheque_no": ["This cheque number is already used on this bank"]},
                )
            if name == "pdc_no_per_agreement_uq":
                return ConflictError(
                    "Two cheques of this agreement share a number", code="duplicate_cheque"
                )
            if name == "ra_renewed_from_uq":
                return ConflictError(
                    "This agreement has already been renewed", code="already_renewed"
                )
            if name == "pdc_replaces_uq":
                return ConflictError(
                    "This bounced cheque already has a replacement", code="already_replaced"
                )
        if state == "23514" and "never deleted" in _message(exc):
            return ConflictError("Cheque records are never deleted", code="cheque_immutable")
        if state == "23514" and "cannot be changed" in _message(exc):
            return ConflictError(_message(exc), code="cheque_immutable")
        return super().translate(exc)

    # ---- shared validation ---------------------------------------------------------------------------------
    def require_branch(self, branch_id: Any, field: str = "branch_id") -> dict[str, Any]:
        b = self.rent.branch(branch_id)
        if b is None:
            raise UnprocessableError(
                "Unknown branch", fields={field: ["Choose a configured branch"]}
            )
        if not b["is_active"]:
            raise UnprocessableError(
                "Branch is inactive", fields={field: ["This branch is inactive"]}
            )
        return b

    @staticmethod
    def schedule_error(exc: rules.ScheduleError) -> UnprocessableError:
        return UnprocessableError(str(exc), fields={exc.field: [str(exc)]})

    def build_lines(
        self,
        rent: Decimal,
        n: int,
        first_date: date,
        first_no: str,
        bank: str,
        override: list[ChequeLineIn] | None,
    ) -> list[rules.ChequeLine]:
        """The generated schedule, or the Owner's reviewed rows after the same checks the database enforces."""
        try:
            generated = rules.build_schedule(rent, n, first_date, first_no, bank)
        except rules.ScheduleError as e:
            raise self.schedule_error(e) from e
        if override is None:
            return generated
        if len(override) != n:
            raise UnprocessableError(
                f"The schedule must have exactly {n} cheques (it has {len(override)})",
                code="schedule_mismatch",
                fields={"cheques": [f"Expected {n} cheques"]},
            )
        total = sum((money(c.amount) for c in override), Decimal("0.00"))
        if total != money(rent):
            raise UnprocessableError(
                f"The cheques add up to {total} AED but the annual rent is {money(rent)} AED",
                code="schedule_total_mismatch",
                fields={"cheques": [f"Cheque total {total} must equal annual rent {money(rent)}"]},
            )
        seen: set[tuple[str, str]] = set()
        for c in override:
            key = (c.bank, c.cheque_no.strip().lower())
            if key in seen:
                raise UnprocessableError(
                    f"Cheque number {c.cheque_no} is used twice on {c.bank}",
                    code="duplicate_cheque",
                    fields={"cheques": [f"Cheque {c.cheque_no} appears twice"]},
                )
            seen.add(key)
        ordered = sorted(override, key=lambda c: (c.cheque_date, c.cheque_no))
        return [
            rules.ChequeLine(i, c.cheque_no.strip(), c.cheque_date, money(c.amount), c.bank)
            for i, c in enumerate(ordered)
        ]

    def insert_schedule(self, agreement_id: Any, lines: list[rules.ChequeLine]) -> None:
        for ln in lines:
            self.rent.insert_cheque(
                {
                    "agreement_id": agreement_id,
                    "cheque_no": ln.cheque_no,
                    "bank": ln.bank,
                    "cheque_date": ln.cheque_date,
                    "amount": ln.amount,
                }
            )


# ---------------------------------------------------------------- row -> model dicts
def timing_of(status: str, cheque_date: date, today: date) -> tuple[str, int | None]:
    if status != "Pending":
        return "done", None
    days = (cheque_date - today).days
    if days < 0:
        return "overdue", days
    if days <= rules.DUE_URGENT_DAYS:
        return "due_7", days
    if days <= rules.DUE_SOON_DAYS:
        return "due_30", days
    return "later", days


def cheque_dict(row: dict[str, Any], today: date, tracking_start: date | None) -> dict[str, Any]:
    timing, days = timing_of(row["status"], row["cheque_date"], today)
    return {
        "id": row["id"],
        "agreement_id": row["agreement_id"],
        "branch_id": row["branch_id"],
        "branch_name": row["branch_name"],
        "landlord": row["landlord"],
        "unit": row["unit"],
        "cheque_no": row["cheque_no"],
        "cheque_date": row["cheque_date"],
        "amount": row["amount"],
        "bank": row["bank"],
        "status": row["status"],
        "cleared_on": row["cleared_on"],
        "bounced_on": row["bounced_on"],
        "notes": row["notes"],
        "replaces_id": row["replaces_id"],
        "replaces_no": row["replaces_no"],
        "replaced_by_id": row["replaced_by_id"],
        "replaced_by_no": row["replaced_by_no"],
        "superseded": bool(row["superseded"]),
        "timing": timing,
        "days_to_due": days,
        "affects_balance": row["status"] == "Cleared"
        and tracking_start is not None
        and row["cheque_date"] >= tracking_start,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "cleared_by_name": row["cleared_by_name"],
        "bounced_by_name": row["bounced_by_name"],
    }


def agreement_dict(row: dict[str, Any], today: date) -> dict[str, Any]:
    return {
        "id": row["id"],
        "branch_id": row["branch_id"],
        "branch_name": row["branch_name"],
        "landlord": row["landlord"],
        "unit": row["unit"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "annual_rent": row["annual_rent"],
        "bank": row["bank"],
        "cheque_count": row["cheque_count"],
        "first_cheque_date": row["first_cheque_date"],
        "first_cheque_no": row["first_cheque_no"],
        "notes": row["notes"],
        "stored_status": row["status"],
        "status": rules.agreement_status(row["status"], row["start_date"], row["end_date"], today),
        "days_to_end": (row["end_date"] - today).days,
        "renewed_from_id": row["renewed_from_id"],
        "renewed_to_id": row["renewed_to_id"],
        "live_cheques": int(row["live_cheques"]),
        "schedule_total": money(row["schedule_total"]),
        "pending_count": int(row["pending_count"]),
        "cleared_count": int(row["cleared_count"]),
        "bounced_count": int(row["bounced_count"]),
        "next_cheque_date": row["next_cheque_date"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "created_by_name": row["created_by_name"],
        "updated_by_name": row["updated_by_name"],
    }


def not_found(what: str) -> NotFoundError:
    return NotFoundError(f"{what} not found")
