"""Centralized Alerts / Notifications (Step 11).

One alert system, not two: the conditions are still computed from the real records by the module services that already
own them (Step 9 compliance, Step 10 rentals / PDC) plus missing daily reports, supplier dues and tasks. This service
only collects them, applies one severity scale, and keeps ONE table row per occurrence (public.alerts) so each can be
marked read / acknowledged and so resolved alerts stay in the history.

Refresh behaviour: `sync()` runs on demand at the start of every alerts read (list, summary, unread count, history) and on
POST /alerts/refresh. It writes only when something changed: a new condition is inserted once (partial unique index on the
open alert key), a changed one is updated in place, a condition that no longer exists is marked resolved. No scheduler is
required for correctness; see docs/tasks/STEP11_TASKS_ALERTS.md for the scheduling note."""

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy.exc import DBAPIError

from app.api.authz import PermissionDeniedError
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.repositories.alert_repository import AlertRepository
from app.schemas.alerts import AlertOut, AlertPage, AlertSummary, UnreadCount
from app.services.base import BaseService
from app.services.compliance_service import ComplianceService
from app.services.dashboard_service import DashboardService
from app.services.finance_core import _message, sqlstate
from app.services.rental_alert_service import RentalAlertService
from app.utils.time import BUSINESS_TZ, dubai_today

logger = logging.getLogger(__name__)

ALERT_LOCK = 80904
RECENT = 5

MODULES = {
    "daily_reports": "Daily Reports",
    "employees": "Employees",
    "visas_passports": "Visas & Passports",
    "trade_licenses": "Trade Licenses",
    "rentals": "Rental Agreements",
    "pdc_cheques": "PDC Cheques",
    "suppliers": "Suppliers",
    "tasks": "Tasks",
}
# kind -> (module, label)
KINDS: dict[str, tuple[str, str]] = {
    "report_missing": ("daily_reports", "Missing daily report"),
    "visa_expired": ("visas_passports", "Visa expired"),
    "visa_expiring": ("visas_passports", "Visa expiring within 30 days"),
    "passport_expired": ("visas_passports", "Passport expired"),
    "passport_expiring": ("visas_passports", "Passport expiring within 30 days"),
    "leave_limit_approaching": ("employees", "Approaching the six-month leave limit"),
    "visa_cancelled_by_leave": ("employees", "Visa cancelled by the six-month leave rule"),
    "license_expired": ("trade_licenses", "Trade licence expired"),
    "license_expiring": ("trade_licenses", "Trade licence expiring within 30 days"),
    "license_renewal_due": ("trade_licenses", "Trade licence renewal approaching"),
    "rental_expired": ("rentals", "Rental agreement ended, not renewed"),
    "rental_ending": ("rentals", "Rental agreement ending within 30 days"),
    "rental_renewal_upcoming": ("rentals", "Rental renewal coming up (31 to 90 days)"),
    "cheque_overdue": ("pdc_cheques", "PDC cheque overdue"),
    "cheque_due_7": ("pdc_cheques", "PDC cheque due within 7 days"),
    "cheque_due_30": ("pdc_cheques", "PDC cheque due in 8 to 30 days"),
    "cheque_bounced": ("pdc_cheques", "PDC cheque bounced"),
    "supplier_dues": ("suppliers", "Supplier outstanding dues"),
    "task_overdue": ("tasks", "Task overdue"),
    "task_due_today": ("tasks", "Task due today"),
    "task_due_7": ("tasks", "Task due within 7 days"),
}
SEVERITY = {"danger": "critical", "warning": "warning", "critical": "critical", "info": "info"}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class AlertService(BaseService):
    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.repo = AlertRepository(session)

    # ---- collecting the real conditions ------------------------------------------------------------------
    def collect(self, today: date) -> list[dict[str, Any]]:
        branches = self.repo.branches()
        out: list[dict[str, Any]] = []

        def add(
            kind: str,
            record_id: str | None,
            severity: str,
            title: str,
            detail: str,
            branch_name: str | None,
            due: date | None,
            href: str,
            branch_id: uuid.UUID | None = None,
            key: str | None = None,
        ) -> None:
            out.append(
                {
                    "alert_key": key or f"{kind}:{record_id}",
                    "kind": kind,
                    "module": KINDS[kind][0],
                    "severity": SEVERITY[severity],
                    "title": title,
                    "detail": detail,
                    "record_id": record_id,
                    "branch_id": branch_id or branches.get(branch_name or ""),
                    "branch_name": branch_name,
                    "due_date": due,
                    "href": href,
                }
            )

        # Step 9: visas, passports, leave rule, trade licences (same conditions, same thresholds)
        for c in ComplianceService(self.session).alerts().items:
            add(
                c.kind,
                c.record_id,
                c.severity,
                c.title,
                c.detail,
                c.branch_name,
                c.due_date,
                c.href,
                key=c.key,
            )
        # Step 10: rental agreements and PDC cheques
        for r in RentalAlertService(self.session).alerts().items:
            rid = r.key.split(":", 1)[1]
            add(
                r.kind,
                rid,
                r.severity,
                r.title,
                r.detail,
                r.branch_name,
                r.due_date,
                r.href,
                key=r.key,
            )
        # Step 7 definition of a missing report, month to date, one alert per branch
        missing = DashboardService(self.session).missing(None, today.replace(day=1), today, today)
        for mb in missing.branches:
            dates = sorted(mb.dates)
            add(
                "report_missing",
                str(mb.branch_id),
                "warning",
                "Daily report not submitted",
                f"{mb.branch_name}: {_plural(mb.missing_count, 'day')} without a daily report this month "
                f"(oldest {dates[0].isoformat()}, latest {dates[-1].isoformat()})",
                mb.branch_name,
                dates[0],
                "/branch-date-view",
                branch_id=mb.branch_id,
            )
        # Suppliers: the only approved rule is "amount owed to suppliers" (informational); see decision S4
        for s in self.repo.supplier_rows():
            add(
                "supplier_dues",
                str(s["record_id"]),
                "info",
                "Supplier has outstanding dues",
                f"{s['name']}: AED {s['outstanding']:,.2f} outstanding",
                None,
                None,
                f"/suppliers/{s['record_id']}",
            )
        # Tasks: overdue = due date passed and not Done (Dubai date); Done tasks never appear
        for t in self.repo.task_rows(today):
            kind = t["kind"]
            days = (t["due_date"] - today).days
            when = (
                f"{_plural(-days, 'day')} overdue"
                if days < 0
                else "due today"
                if days == 0
                else f"due in {_plural(days, 'day')}"
            )
            add(
                kind,
                str(t["record_id"]),
                {"task_overdue": "warning", "task_due_today": "warning", "task_due_7": "info"}[
                    kind
                ],
                KINDS[kind][1],
                f"{t['title']} ({t['branch_name']}, {t['assignee']}): {when}",
                None if t["branch_id"] is None else t["branch_name"],
                t["due_date"],
                f"/tasks/{t['record_id']}",
                branch_id=t["branch_id"],
            )
        return out

    # ---- keeping the table in step with reality ----------------------------------------------------------
    def sync(self) -> bool:
        """Insert new conditions, update changed ones, resolve vanished ones. Returns True when anything was written."""
        today = dubai_today()
        try:
            self.repo.lock(ALERT_LOCK)
            current = {a["alert_key"]: a for a in self.collect(today)}
            existing = {r["alert_key"]: r for r in self.repo.open_rows()}
            changed = False
            for key, a in current.items():
                row = existing.get(key)
                if row is None:
                    self.repo.insert(a)
                    changed = True
                    continue
                fields = (
                    "severity",
                    "title",
                    "detail",
                    "branch_id",
                    "branch_name",
                    "due_date",
                    "href",
                )
                if any(row[f] != a[f] for f in fields):
                    self.repo.refresh(row["id"], a)
                    changed = True
            gone = [r["id"] for k, r in existing.items() if k not in current]
            if gone:
                self.repo.resolve(gone)
                changed = True
            if changed:
                self.session.commit()
            else:
                self.session.rollback()  # releases the advisory lock; nothing was written
            return changed
        except DBAPIError as exc:
            self.session.rollback()
            if sqlstate(exc) == "42501":
                raise PermissionDeniedError() from exc
            logger.warning("alert sync failed: %s", _message(exc))
            raise

    # ---- reads -------------------------------------------------------------------------------------------
    def _out(self, r: dict[str, Any]) -> AlertOut:
        return AlertOut(
            **{
                k: r[k]
                for k in (
                    "id",
                    "alert_key",
                    "kind",
                    "module",
                    "title",
                    "detail",
                    "record_id",
                    "branch_id",
                    "branch_name",
                    "due_date",
                    "severity",
                    "status",
                    "href",
                    "first_seen_at",
                    "last_seen_at",
                    "read_at",
                    "acknowledged_at",
                    "resolved_at",
                )
            },  # fmt: skip
            type_label=KINDS.get(r["kind"], (r["module"], r["kind"]))[1],
            alert_date=r["first_seen_at"].astimezone(BUSINESS_TZ).date(),
        )

    def summary(self) -> AlertSummary:
        self.sync()
        c = self.repo.counts()
        rows, _ = self.repo.search("active", None, None, None, None, None, None, 1, RECENT)
        return AlertSummary(
            total_active=int(c["total_active"]),
            critical=int(c["critical"]),
            warning=int(c["warning"]),
            info=int(c["info"]),
            unread=int(c["unread"]),
            acknowledged=int(c["acknowledged"]),
            recent=[self._out(r) for r in rows],
            by_module=self.repo.by_module(),
        )

    def unread_count(self) -> UnreadCount:
        self.sync()
        c = self.repo.counts()
        return UnreadCount(unread=int(c["unread"]), total_active=int(c["total_active"]))

    def search(
        self,
        scope: str,
        q: str | None,
        kind: str | None,
        severity: str | None,
        branch_id: uuid.UUID | None,
        module: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> AlertPage:
        self.sync()
        rows, total = self.repo.search(
            scope, q, kind, severity, branch_id, module, status, page, page_size
        )
        return AlertPage(
            items=[self._out(r) for r in rows], total=total, page=page, page_size=page_size
        )

    def facets(self) -> dict[str, list[tuple[str, str]]]:
        return {
            "kinds": [(k, v[1]) for k, v in KINDS.items()],
            "modules": list(MODULES.items()),
        }

    # ---- state changes -----------------------------------------------------------------------------------
    def _open(self, id_: uuid.UUID) -> dict[str, Any]:
        row = self.repo.get(id_, for_update=True)
        if row is None:
            raise NotFoundError("Alert not found")
        if row["resolved_at"] is not None:
            raise ConflictError(
                "This alert is resolved: the issue no longer exists", code="alert_resolved"
            )
        return row

    def _change(self, id_: uuid.UUID, fn: Any) -> AlertOut:
        try:
            self.sync()  # first reconcile, so an alert whose issue was just fixed is reported as resolved
            self._open(id_)
            fn(id_)
            self.session.commit()
        except DBAPIError as exc:
            self.session.rollback()
            if sqlstate(exc) == "42501":
                raise PermissionDeniedError() from exc
            raise UnprocessableError(_message(exc) or "The alert could not be updated") from exc
        except Exception:
            self.session.rollback()
            raise
        row = self.repo.get(id_)
        assert row is not None
        return self._out(row)

    def mark_read(self, id_: uuid.UUID) -> AlertOut:
        return self._change(id_, self.repo.mark_read)

    def acknowledge(self, id_: uuid.UUID) -> AlertOut:
        return self._change(id_, self.repo.acknowledge)

    def read_all(self) -> UnreadCount:
        self.sync()
        self.repo.read_all()
        self.session.commit()
        return self.unread_count()
