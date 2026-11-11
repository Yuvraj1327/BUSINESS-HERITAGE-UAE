import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api.authz import BranchAccessDeniedError, BranchScope
from app.core import calculations as calc
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.repositories.report_repository import ReportRepository
from app.schemas.reports import DailyReportCreate, DailyReportOut, DailyReportPage
from app.services.base import BaseService
from app.utils.time import dubai_today

logger = logging.getLogger(__name__)

# PostgreSQL SQLSTATE codes we translate into API errors
_UNIQUE, _CHECK, _FK, _RLS = "23505", "23514", "23503", "42501"


def report_out(row: dict[str, Any]) -> DailyReportOut:
    """Row -> API model, adding every computed field through app.core.calculations (the only place they exist)."""
    received = calc.total_received(
        row["cash_received"], row["pos_amount"], row["bank_transfer"], row["link_payment"]
    )
    diff = calc.difference(row["total_sales"], received)
    return DailyReportOut(
        **{
            k: row[k]
            for k in (
                "id",
                "report_date",
                "branch_id",
                "branch_name",
                "total_sales",
                "order_count",
                "cash_received",
                "pos_amount",
                "bank_transfer",
                "link_payment",
                "shop_expenses",
                "shop_savings",
                "created_at",
            )
        },
        total_received=received,
        difference=diff,
        check=calc.check_label(diff),
        shop_expenses_excl_savings=calc.shop_expenses_excl_savings(
            row["shop_expenses"], row["shop_savings"]
        ),
    )


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


class ReportService(BaseService):
    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.repo = ReportRepository(session)

    # ---- submit ----------------------------------------------------------------------------------------
    def create(
        self, scope: BranchScope, body: DailyReportCreate, today: date | None = None
    ) -> DailyReportOut:
        today = today or dubai_today()
        branch_id = self._branch_for_submit(scope, body.branch_id)
        report_date = body.report_date or today
        if report_date > today:
            raise UnprocessableError(
                "Report date cannot be in the future (Dubai time)",
                fields={
                    "report_date": [
                        f"Report date cannot be after today in Dubai ({today.isoformat()})"
                    ]
                },
            )
        try:
            new_id = self.repo.insert(branch_id, report_date, body.model_dump(mode="python"))
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise self._translate(exc) from exc
        except DBAPIError as exc:
            self.session.rollback()
            raise self._translate(exc) from exc
        row = self.repo.get(new_id)
        assert row is not None  # we just inserted it under the same session
        return report_out(row)

    def _branch_for_submit(self, scope: BranchScope, requested: uuid.UUID | None) -> uuid.UUID:
        if scope.is_all:
            if requested is None:
                raise UnprocessableError(
                    "Select a branch", fields={"branch_id": ["Select a branch"]}
                )
            found = self.repo.get_branch(requested)
            if found is None or not found["is_active"]:
                raise UnprocessableError(
                    "Unknown or inactive branch", fields={"branch_id": ["Select an active branch"]}
                )
            return requested
        # Branch user: the branch is the one on their profile. A different id in the payload is an attack or a
        # stale form, and is refused (and audited) rather than silently replaced.
        own = scope.resolve(requested)
        assert own is not None
        return own

    @staticmethod
    def _translate(exc: DBAPIError) -> Exception:
        state = _sqlstate(exc)
        text = str(getattr(exc.orig, "diag", None) and exc.orig.diag.constraint_name or "")  # type: ignore[union-attr]
        if state == _UNIQUE:
            return ConflictError(
                "A report for this branch and date already exists",
                code="duplicate_report",
                fields={"report_date": ["A report for this branch and date already exists"]},
            )
        if state == _RLS:
            return BranchAccessDeniedError()
        if state == _FK:
            return UnprocessableError(
                "Unknown branch", fields={"branch_id": ["Select an active branch"]}
            )
        if state == _CHECK:
            message = str(exc.orig).splitlines()[0] if exc.orig else "Report breaks a business rule"
            if "future" in message:
                return UnprocessableError(
                    "Report date cannot be in the future (Dubai time)",
                    fields={"report_date": ["Report date cannot be in the future"]},
                )
            logger.warning("report rejected by database check %s", text)
            return UnprocessableError("The report breaks a business rule")
        raise exc

    # ---- read ------------------------------------------------------------------------------------------
    def list(
        self,
        scope: BranchScope,
        branch_id: uuid.UUID | None,
        d_from: date | None,
        d_to: date | None,
        page: int,
        page_size: int,
    ) -> DailyReportPage:
        if d_from and d_to and d_from > d_to:
            raise UnprocessableError(
                "Start date is after end date",
                fields={"date_from": ["Start date must not be after end date"]},
            )
        branch = scope.resolve(branch_id)
        rows, total = self.repo.list_page(branch, d_from, d_to, page_size, (page - 1) * page_size)
        return DailyReportPage(
            items=[report_out(r) for r in rows], total=total, page=page, page_size=page_size
        )

    def get(self, scope: BranchScope, report_id: uuid.UUID) -> DailyReportOut:
        row = self.repo.get(report_id)
        if row is None:
            # RLS hides other branches' rows, so "not yours" and "does not exist" look the same.
            raise NotFoundError("Report not found")
        scope.ensure(row["branch_id"])
        return report_out(row)

    # ---- owner correction (decision D4: audited void; the database function checks the role again) --------
    def void(self, report_id: uuid.UUID, reason: str) -> None:
        try:
            self.repo.void(report_id, reason)
            self.session.commit()
        except DBAPIError as exc:
            self.session.rollback()
            state = _sqlstate(exc)
            if state == "P0002":  # no_data_found
                raise NotFoundError("Report not found or already voided") from exc
            if state == _RLS:
                raise BranchAccessDeniedError() from exc
            if state == _CHECK:
                raise UnprocessableError(
                    "A reason is required", fields={"reason": ["A reason is required"]}
                ) from exc
            raise
