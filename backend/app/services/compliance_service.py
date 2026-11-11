"""Visas & passports dashboard and the per-record compliance alert feed (Owner-only)."""

import uuid
from datetime import date
from typing import Any, Literal

from app.core import calculations as calc
from app.core.exceptions import ConflictError, UnprocessableError
from app.schemas.hr import (
    AlertFeed,
    BucketCounts,
    ComplianceAlert,
    CompliancePage,
    ComplianceRow,
    ComplianceSummary,
    EmployeeDetail,
    ExpiryChange,
    ExpiryUpdateIn,
)
from app.services.employee_service import EmployeeService
from app.services.hr_core import HR_LOCK, HrCore, employee_dict, not_found
from app.utils.time import dubai_today

Kind = Literal["visa", "passport"]
COLUMN = {"visa": "visa_expiry", "passport": "passport_expiry"}


def _days_text(due: date | None, today: date) -> tuple[int | None, str]:
    if due is None:
        return None, ""
    n = (due - today).days
    if n < 0:
        return n, f"expired {-n} day{'s' if n != -1 else ''} ago"
    return n, "expires today" if n == 0 else f"expires in {n} day{'s' if n != 1 else ''}"


ALERTS: dict[str, tuple[str, str, str]] = {
    # kind: (severity, title template, link base)
    "visa_expired": ("danger", "Visa expired", "/employees/"),
    "visa_expiring": ("danger", "Visa expiring within 30 days", "/employees/"),
    "passport_expired": ("danger", "Passport expired", "/employees/"),
    "passport_expiring": ("danger", "Passport expiring within 30 days", "/employees/"),
    "leave_limit_approaching": ("warning", "Approaching the six-month leave limit", "/employees/"),
    "visa_cancelled_by_leave": (
        "danger",
        "Visa cancelled: six-month leave limit passed",
        "/employees/",
    ),
    "license_expired": ("danger", "Trade licence expired", "/trade-licenses/"),
    "license_expiring": ("danger", "Trade licence expiring within 30 days", "/trade-licenses/"),
    "license_renewal_due": ("warning", "Trade licence renewal approaching", "/trade-licenses/"),
}


class ComplianceService(HrCore):
    def _row(self, r: dict[str, Any], kind: Kind, today: date) -> ComplianceRow:
        status: str
        days: int | None
        if kind == "visa" and r["eff_cancelled"]:
            status, days = "cancelled", None
        elif kind == "visa":
            status, days = calc.visa_status(r["expiry_date"], today)
        else:
            status, days = calc.passport_status(r["expiry_date"], today)
        return ComplianceRow(
            employee_id=r["employee_id"],
            employee_name=r["employee_name"],
            branch_id=r["branch_id"],
            branch_name=r["branch_name"],
            employment_status=("Visa Cancelled" if r["eff_cancelled"] else r["employment_status"]),
            expiry_date=r["expiry_date"],
            status=status,  # type: ignore[arg-type]
            days_remaining=days,
        )

    def search(
        self,
        kind: Kind,
        q: str | None,
        branch_id: uuid.UUID | None,
        bucket: str | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> CompliancePage:
        today = dubai_today()
        rows, total = self.hr.compliance(
            kind, today, q, branch_id, bucket, sort, desc, page, page_size
        )
        return CompliancePage(
            items=[self._row(r, kind, today) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def summary(self) -> ComplianceSummary:
        today = dubai_today()
        v, p = (
            self.hr.compliance_counts("visa", today),
            self.hr.compliance_counts("passport", today),
        )

        def buckets(r: dict[str, Any]) -> BucketCounts:
            return BucketCounts(
                **{
                    k: int(r[k])
                    for k in (
                        "expired",
                        "urgent",
                        "upcoming",
                        "normal",
                        "not_recorded",
                        "cancelled",
                    )
                }
            )

        a = self.hr.alert_rows(today)
        return ComplianceSummary(
            visas=buckets(v),
            passports=buckets(p),
            visas_expiring_30=sum(1 for r in a if r["kind"] == "visa_expiring"),
            passports_expiring_30=sum(1 for r in a if r["kind"] == "passport_expiring"),
            passports_under_6_months=int(p["urgent"]) + int(p["upcoming"]),
            visas_cancelled=int(v["cancelled"]),
        )

    def update_expiry(self, id_: uuid.UUID, kind: Kind, body: ExpiryUpdateIn) -> EmployeeDetail:
        def work() -> None:
            today = dubai_today()
            self.hr.lock(HR_LOCK)
            row = self.hr.employee(id_, today, for_update=True)
            if row is None:
                raise not_found("Employee")
            if row["archived_at"] is not None:
                raise ConflictError("This employee is archived", code="employee_archived")
            if kind == "visa" and employee_dict(row, today)["visa_cancelled"]:
                raise UnprocessableError(
                    "The visa is cancelled; its expiry date can no longer be changed",
                    fields={"expiry_date": ["The visa is cancelled"]},
                )
            col = COLUMN[kind]
            if row[col] == body.expiry_date:
                raise UnprocessableError(
                    "The expiry date is unchanged",
                    fields={"expiry_date": ["Enter a different date"]},
                )
            self.hr.set_reason(body.reason)
            self.hr.set_expiry(id_, col, body.expiry_date)
            self.session.commit()

        self.run(work)
        return EmployeeService(self.session).detail(id_)

    def history(self, id_: uuid.UUID, kind: Kind) -> list[ExpiryChange]:
        if self.hr.employee(id_, dubai_today()) is None:
            raise not_found("Employee")
        rows = self.hr.expiry_history(id_, COLUMN[kind])
        return [
            ExpiryChange(
                occurred_at=r["occurred_at"],
                actor_name=r["actor_name"],
                old_expiry=date.fromisoformat(r["old_expiry"]) if r["old_expiry"] else None,
                new_expiry=date.fromisoformat(r["new_expiry"]) if r["new_expiry"] else None,
                reason=r["reason"],
            )
            for r in rows
        ]

    def alerts(self) -> AlertFeed:
        today = dubai_today()
        items: list[ComplianceAlert] = []
        for r in self.hr.alert_rows(today):
            severity, title, base = ALERTS[r["kind"]]
            days, text = _days_text(r["due"], today)
            who = f"{r['name']} ({r['branch_name']})"
            if r["kind"] == "leave_limit_approaching":
                text = text.replace("expires", "limit reached")
            elif r["kind"] == "visa_cancelled_by_leave":
                text = f"limit passed {abs(days or 0)} day{'s' if abs(days or 0) != 1 else ''} ago"
            items.append(
                ComplianceAlert(
                    key=f"{r['kind']}:{r['record_id']}",
                    branch_name=r["branch_name"],
                    record_id=str(r["record_id"]),
                    kind=r["kind"],
                    severity=severity,  # type: ignore[arg-type]
                    title=title,
                    detail=f"{who}: {text}",
                    due_date=r["due"],
                    days_remaining=days,
                    href=f"{base}{r['record_id']}",
                )
            )
        return AlertFeed(
            items=items,
            total=len(items),
            danger=sum(1 for i in items if i.severity == "danger"),
            warning=sum(1 for i in items if i.severity == "warning"),
        )
