"""Shared Step 9 plumbing: error mapping, transactions, row -> API model conversion."""

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.authz import PermissionDeniedError
from app.core import calculations as calc
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.repositories.hr_repository import HrRepository
from app.services.base import BaseService
from app.services.finance_core import _message, constraint, sqlstate

logger = logging.getLogger(__name__)

HR_LOCK = (
    80902  # serialises employee state changes and licence renewals (race-safe repeat prevention)
)


def need_reason(reason: str | None, what: str) -> str:
    if not reason or len(reason.strip()) < 3:
        raise UnprocessableError(
            f"A reason (at least 3 characters) is required {what}",
            code="reason_required",
            fields={"reason": [f"Enter a reason {what}"]},
        )
    return reason.strip()


class HrCore(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.hr = HrRepository(session)

    def translate(self, exc: DBAPIError) -> Exception:
        state, name = sqlstate(exc), constraint(exc)
        if state == "23505":
            if "client_key" in name:
                return ConflictError(
                    "This action was already recorded (duplicate submission)",
                    code="duplicate_transaction",
                )
            if name == "trade_licenses_no_uq":
                return ConflictError(
                    "A trade licence with this number already exists",
                    code="duplicate_license",
                    fields={"license_no": ["A trade licence with this number already exists"]},
                )
            return ConflictError("This record already exists", code="duplicate")
        if state == "42501":
            return PermissionDeniedError()
        if state in ("23514", "23503"):
            return UnprocessableError(_message(exc) or "The record breaks a rule")
        logger.warning("unmapped database error %s %s", state, name)
        return exc

    def run(self, fn: Any) -> Any:
        try:
            return fn()
        except DBAPIError as exc:
            self.session.rollback()
            mapped = self.translate(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        except Exception:
            self.session.rollback()
            raise

    def require_branch(self, branch_id: uuid.UUID, field: str = "branch_id") -> dict[str, Any]:
        b = self.hr.branch_exists(branch_id)
        if b is None:
            raise UnprocessableError(
                "Unknown branch", fields={field: ["Choose one of the configured branches"]}
            )
        if not b["is_active"]:
            raise UnprocessableError(
                "Branch is inactive", fields={field: ["This branch is inactive"]}
            )
        return b


def employee_dict(row: dict[str, Any], today: date) -> dict[str, Any]:
    """DB row -> EmployeeOut dict. Every status is derived from dates here (and in SQL for filters), never typed."""
    stored = row["status"]
    leave = None
    cancelled = bool(row["visa_cancelled"])
    cancelled_date = row["visa_cancelled_date"]
    if stored == "Leave" and row["leave_start"] is not None:
        info = calc.leave_info(row["leave_start"], today, cancelled)
        leave = {
            "leave_start": info.leave_start,
            "limit_date": info.limit_date,
            "days_on_leave": info.days_on_leave,
            "days_remaining": info.days_remaining,
            "state": info.state,
        }
        if info.state == "visa_cancelled" and not cancelled:
            cancelled = True  # cancelled by the six-month rule (not yet recorded permanently)
            cancelled_date = cancelled_date or info.limit_date
    status = "Visa Cancelled" if cancelled else ("On Leave" if stored == "Leave" else "Active")
    if cancelled:
        visa_state, visa_days = "cancelled", None
    else:
        visa_state, visa_days = calc.visa_status(row["visa_expiry"], today)
    pass_state, pass_days = calc.passport_status(row["passport_expiry"], today)
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "branch_id": row["branch_id"],
        "branch_name": row["branch_name"],
        "role_title": row["role_title"],
        "monthly_salary": row["monthly_salary"],
        "status": status,
        "stored_status": stored,
        "leave": leave,
        "visa_cancelled": cancelled,
        "visa_cancelled_date": cancelled_date,
        "visa_expiry": row["visa_expiry"],
        "visa_status": visa_state,
        "visa_days_remaining": visa_days,
        "passport_expiry": row["passport_expiry"],
        "passport_status": pass_state,
        "passport_days_remaining": pass_days,
        "notes": row["notes"],
        "payroll_eligible": stored == "Active" and not cancelled and row["archived_at"] is None,
        "archived": row["archived_at"] is not None,
        "archive_reason": row["archive_reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "created_by_name": row["created_by_name"],
        "updated_by_name": row["updated_by_name"],
    }


def license_dict(row: dict[str, Any], today: date) -> dict[str, Any]:
    status, days = calc.license_status(row["expiry_date"], today)
    return {
        "id": row["id"],
        "branch_id": row["branch_id"],
        "branch_name": row["branch_name"],
        "license_no": row["license_no"],
        "authority": row["authority"],
        "expiry_date": row["expiry_date"],
        "renewal_fee": row["renewal_fee"],
        "notes": row["notes"],
        "status": status,
        "days_remaining": days,
        "renewal_count": int(row["renewal_count"]),
        "last_renewed_on": row["last_renewed_on"],
        "archived": row["archived_at"] is not None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "updated_by_name": row["updated_by_name"],
    }


def not_found(what: str) -> NotFoundError:
    return NotFoundError(f"{what} not found")
