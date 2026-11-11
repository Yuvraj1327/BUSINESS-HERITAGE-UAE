"""Shared finance rules: configuration state, dates, available funds, negative-balance guard, DB error mapping."""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.authz import PermissionDeniedError
from app.core.calculations import money
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.repositories.finance_repository import FinanceRepository
from app.services.base import BaseService
from app.utils.time import dubai_today

logger = logging.getLogger(__name__)

_ACCOUNT_COLUMN = {
    "Cash": "cash_now",
    "ENBD": "enbd_now",
    "ADCB": "adcb_now",
    "POS Pending": "pos_pending",
}


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def constraint(exc: DBAPIError) -> str:
    diag = getattr(exc.orig, "diag", None)
    return str(getattr(diag, "constraint_name", "") or "")


def _message(exc: DBAPIError) -> str:
    diag = getattr(exc.orig, "diag", None)
    return str(getattr(diag, "message_primary", "") or "")


class FinanceCore(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.fin = FinanceRepository(session)

    # ---- state -------------------------------------------------------------------------------------------
    def tracking_start(self) -> date | None:
        ob = self.fin.opening()
        return None if ob is None else ob["as_of_date"] + timedelta(days=1)

    def require_configured(self) -> date:
        start = self.tracking_start()
        if start is None:
            raise ConflictError(
                "Opening balances are not configured yet. The Owner must save them first.",
                code="opening_not_configured",
            )
        return start

    def resolve_date(self, value: date | None, field: str, today: date | None = None) -> date:
        """Default today (Dubai); never future; never before the tracking start (those days are not tracked)."""
        today = today or dubai_today()
        start = self.require_configured()
        d = value or today
        if d > today:
            raise UnprocessableError(
                "Date cannot be in the future (Dubai time)",
                fields={field: [f"Date cannot be after today in Dubai ({today.isoformat()})"]},
            )
        if d < start:
            raise UnprocessableError(
                "Date is before financial tracking started",
                fields={
                    field: [
                        f"Tracking starts on {start.isoformat()}, the day after the opening balance date"
                    ]
                },
            )
        return d

    # ---- funds -------------------------------------------------------------------------------------------
    def available(self, account: str, as_of: date, branch: uuid.UUID | None = None) -> Decimal:
        if account == "Cash" and branch is not None:
            for r in self.fin.branch_cash(as_of):
                if r["branch_id"] == branch:
                    return money(r["closing"])
            return money(0)
        return money(self.fin.balances(as_of)[_ACCOUNT_COLUMN[account]])

    def ensure_funds(
        self,
        account: str,
        amount: Decimal,
        on: date,
        field: str = "amount",
        branch: uuid.UUID | None = None,
        branch_only: bool = False,
    ) -> None:
        """No overdraft rule is approved, so an outflow may never exceed the account balance on its date or today."""
        today = dubai_today()
        for d in {on, today}:
            have = self.available(account, d, branch if branch_only else None)
            if have < amount:
                where = account if not branch_only else f"{account} (selected branch)"
                raise UnprocessableError(
                    f"Not enough funds in {where}: available {have} AED on {d.isoformat()}",
                    code="insufficient_funds",
                    fields={field: [f"Only {have} AED is available in {where}"]},
                )

    def ensure_no_negative_balances(self, branches: tuple[uuid.UUID, ...] = ()) -> None:
        """After a correction/void: nothing may end below zero (called before commit; the caller rolls back)."""
        b = self.fin.balances(dubai_today())
        for label, col in (
            ("Cash", "cash_now"),
            ("ENBD", "enbd_now"),
            ("ADCB", "adcb_now"),
            ("POS Pending", "pos_pending"),
        ):
            if money(b[col]) < 0:
                raise UnprocessableError(
                    f"This change would leave {label} negative", code="negative_balance"
                )
        wanted = set(branches)
        for r in self.fin.branch_cash(dubai_today()):
            if r["branch_id"] in wanted and money(r["closing"]) < 0:
                raise UnprocessableError(
                    f"This change would leave the cash of {r['branch_name']} negative",
                    code="negative_balance",
                )
        if self.fin.negative_suppliers():
            raise UnprocessableError(
                "This change would leave a supplier with a negative balance",
                code="negative_balance",
            )

    # ---- errors ------------------------------------------------------------------------------------------
    def translate(self, exc: DBAPIError) -> Exception:
        state, name = sqlstate(exc), constraint(exc)
        if state == "23505":
            if "client_key" in name:
                return ConflictError(
                    "This entry was already recorded (duplicate submission)",
                    code="duplicate_transaction",
                )
            if name == "suppliers_name_uq":
                return ConflictError(
                    "A supplier with this name already exists",
                    code="duplicate_supplier",
                    fields={"name": ["A supplier with this name already exists"]},
                )
            return ConflictError("This record already exists", code="duplicate")
        if state == "42501":
            return PermissionDeniedError()
        if state == "P0002":
            msg = _message(exc)
            if "opening balances" in msg:
                return ConflictError(
                    "Opening balances are not configured yet.", code="opening_not_configured"
                )
            return NotFoundError("Record not found or already voided")
        if state in ("23514", "23503"):
            return UnprocessableError(_message(exc) or "The record breaks a rule")
        logger.warning("unmapped database error %s %s", state, name)
        return exc

    def run(self, fn: Any) -> Any:
        """Execute a write inside the request transaction; map database errors; roll back on any failure."""
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
