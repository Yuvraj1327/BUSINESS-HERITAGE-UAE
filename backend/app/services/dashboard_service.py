import calendar
import uuid
from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.api.authz import BranchScope
from app.core import calculations as calc
from app.core.calculations import ZERO, money
from app.core.exceptions import UnprocessableError
from app.core.permissions import Action, Module
from app.repositories.report_repository import (
    AlertRepository,
    BalanceRepository,
    HeadOfficeRepository,
    ReportRepository,
)
from app.schemas.dashboard import (
    Alert,
    BalanceSummary,
    BranchDateView,
    BranchRow,
    Collections,
    DayRow,
    HeadOfficeRow,
    HeadOfficeSummary,
    Kpis,
    MissingBranch,
    MissingReports,
    OwnerDashboard,
    Totals,
)
from app.services.base import BaseService
from app.services.report_service import report_out
from app.utils.time import dubai_today

MAX_RANGE_DAYS = 92  # BUSINESS_LOGIC §11


def _totals(sums: dict[str, Any]) -> Totals:
    received = calc.total_received(
        sums["cash_received"], sums["pos_amount"], sums["bank_transfer"], sums["link_payment"]
    )
    return Totals(
        report_count=int(sums["report_count"]),
        total_sales=money(sums["total_sales"]),
        total_orders=int(sums["total_orders"]),
        collections=Collections(
            cash_received=money(sums["cash_received"]),
            pos_amount=money(sums["pos_amount"]),
            bank_transfer=money(sums["bank_transfer"]),
            link_payment=money(sums["link_payment"]),
            total_received=received,
        ),
        not_yet_received=calc.not_yet_received(sums["total_sales"], received),
        shop_expenses=money(sums["shop_expenses"]),
        shop_savings=money(sums["shop_savings"]),
        shop_expenses_excl_savings=calc.shop_expenses_excl_savings(
            sums["shop_expenses"], sums["shop_savings"]
        ),
    )


def _ho(total: Any, savings: Any, count: int) -> HeadOfficeSummary:
    return HeadOfficeSummary(
        total=money(total),
        savings=money(savings),
        excl_savings=calc.head_office_excl_savings(money(total), money(savings)),
        count=count,
    )


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = int(month[:4]), int(month[5:7])
    return date(year, mon, 1), date(year, mon, calendar.monthrange(year, mon)[1])


ALERT_LINKS = {
    "tasks_overdue": "/tasks?view=overdue",
    "tasks_due_today": "/tasks?view=today",
    "tasks_due_7": "/tasks?view=week",
    "visas_30": "/visas-passports",
    "visas_cancelled": "/employees?status=Visa+Cancelled",
    "leave_limit_30": "/employees?status=On+Leave",
    "passports_30": "/visas-passports",
    "licenses_30": "/trade-licenses",
    "licenses_renewal_90": "/trade-licenses",
    "rentals_ending_30": "/rentals",
    "rentals_renewal_90": "/rentals",
    "rentals_expired": "/rentals",
    "cheques_bounced": "/pdc-cheques?view=bounced_open",
    "pdc_overdue": "/pdc-cheques?view=overdue",
    "pdc_due_7": "/pdc-cheques?view=upcoming",
    "pdc_due_30": "/pdc-cheques?view=upcoming",
}


class DashboardService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.reports = ReportRepository(session)
        self.head_office = HeadOfficeRepository(session)

    # ---- missing reports ---------------------------------------------------------------------------------
    def missing(
        self, branch: uuid.UUID | None, d_from: date, d_to: date, today: date
    ) -> MissingReports:
        """Branches/days without a report. Counts only days from the reporting start up to today (Dubai)."""
        start = self.reports.reporting_start()
        if start is None:
            return MissingReports(
                status="not_configured",
                reporting_start=None,
                date_from=None,
                date_to=None,
                expected=0,
                received=0,
                missing_count=0,
                branches=[],
            )
        eff_from, eff_to = max(d_from, start), min(d_to, today)
        if d_to < start:
            return MissingReports(
                status="before_start",
                reporting_start=start,
                date_from=None,
                date_to=None,
                expected=0,
                received=0,
                missing_count=0,
                branches=[],
            )
        if eff_from > eff_to:  # whole range is in the future: nothing is due yet
            return MissingReports(
                status="ok",
                reporting_start=start,
                date_from=None,
                date_to=None,
                expected=0,
                received=0,
                missing_count=0,
                branches=[],
            )
        cells = self.reports.missing_cells(branch, eff_from, eff_to)
        by_branch: dict[uuid.UUID, MissingBranch] = {}
        for c in cells:
            mb = by_branch.setdefault(
                c["branch_id"],
                MissingBranch(
                    branch_id=c["branch_id"],
                    branch_name=c["branch_name"],
                    missing_count=0,
                    dates=[],
                ),
            )
            mb.dates.append(c["day"])
            mb.missing_count += 1
        n_days = (eff_to - eff_from).days + 1
        expected = n_days * self.reports.active_branch_count(branch)
        return MissingReports(
            status="ok",
            reporting_start=start,
            date_from=eff_from,
            date_to=eff_to,
            expected=expected,
            received=expected - len(cells),
            missing_count=len(cells),
            branches=list(by_branch.values()),
        )

    # ---- Branch & Date View ------------------------------------------------------------------------------
    def branch_date_view(
        self,
        scope: BranchScope,
        branch_id: uuid.UUID | None,
        d_from: date,
        d_to: date,
        today: date | None = None,
    ) -> BranchDateView:
        today = today or dubai_today()
        self._check_range(d_from, d_to, today)
        branch = scope.resolve(branch_id)
        rows = self.reports.list_range(branch, d_from, d_to)
        include_ho = scope.principal.can(Module.EXPENSES, Action.READ)
        ho_summary = ho_rows = ho_unalloc = None
        if include_ho:
            ho_summary, ho_rows, ho_unalloc = self._head_office(branch, d_from, d_to)
        return BranchDateView(
            branch_id=branch,
            date_from=d_from,
            date_to=d_to,
            totals=_totals(self.reports.totals(branch, d_from, d_to)),
            reports=[report_out(r) for r in rows],
            missing=self.missing(branch, d_from, d_to, today),
            head_office=ho_summary,
            head_office_rows=ho_rows,
            head_office_unallocated=ho_unalloc,
        )

    def _head_office(
        self, branch: uuid.UUID | None, d_from: date, d_to: date
    ) -> tuple[HeadOfficeSummary, list[HeadOfficeRow], HeadOfficeSummary | None]:
        by_branch = self.head_office.by_branch(d_from, d_to)
        if branch is None:
            total = sum((r["total"] for r in by_branch.values()), ZERO)
            savings = sum((r["savings"] for r in by_branch.values()), ZERO)
            count = sum(int(r["cnt"]) for r in by_branch.values())
            unalloc = None
        else:
            r = by_branch.get(branch, {"total": ZERO, "savings": ZERO, "cnt": 0})
            total, savings, count = r["total"], r["savings"], int(r["cnt"])
            u = by_branch.get(None, {"total": ZERO, "savings": ZERO, "cnt": 0})
            unalloc = _ho(u["total"], u["savings"], int(u["cnt"]))
        rows = [HeadOfficeRow(**r) for r in self.head_office.rows(branch, d_from, d_to)]
        return _ho(total, savings, count), rows, unalloc

    @staticmethod
    def _check_range(d_from: date, d_to: date, today: date) -> None:
        if d_from > d_to:
            raise UnprocessableError(
                "Start date is after end date",
                fields={"date_from": ["Start date must not be after end date"]},
            )
        if d_to > today:
            raise UnprocessableError(
                "End date cannot be in the future",
                fields={"date_to": ["End date cannot be after today (Dubai)"]},
            )
        if (d_to - d_from).days + 1 > MAX_RANGE_DAYS:
            raise UnprocessableError(
                f"Choose at most {MAX_RANGE_DAYS} days",
                fields={"date_from": [f"Choose at most {MAX_RANGE_DAYS} days"]},
            )

    # ---- Owner dashboard ---------------------------------------------------------------------------------
    def owner_dashboard(
        self,
        mode: Literal["day", "month"],
        day: date | None,
        month: str | None,
        today: date | None = None,
    ) -> OwnerDashboard:
        today = today or dubai_today()
        if mode == "day":
            d_from = d_to = day or today
            if d_from > today:
                raise UnprocessableError(
                    "Date cannot be in the future",
                    fields={"date": ["Date cannot be after today (Dubai)"]},
                )
        else:
            month = month or today.strftime("%Y-%m")
            d_from, d_to = month_bounds(month)
            if d_from > today:
                raise UnprocessableError(
                    "Month cannot be in the future",
                    fields={"month": ["Month cannot be after the current month"]},
                )

        totals = _totals(self.reports.totals(None, d_from, d_to))
        ho_by_branch = self.head_office.by_branch(d_from, d_to)
        ho_total = sum((r["total"] for r in ho_by_branch.values()), ZERO)
        ho_savings = sum((r["savings"] for r in ho_by_branch.values()), ZERO)
        ho_excl = calc.head_office_excl_savings(money(ho_total), money(ho_savings))
        missing = self.missing(None, d_from, d_to, today)
        balances = self._balances(min(d_to, today))

        kpis = Kpis(
            total_sales=totals.total_sales,
            total_received=totals.collections.total_received,
            not_yet_received=totals.not_yet_received,
            shop_expenses_excl_savings=totals.shop_expenses_excl_savings,
            head_office_expenses_excl_savings=ho_excl,
            total_savings=calc.total_savings(totals.shop_savings, money(ho_savings)),
            sales_minus_expenses=calc.sales_minus_expenses(
                totals.total_sales, totals.shop_expenses_excl_savings, ho_excl
            ),
            total_orders=totals.total_orders,
            cash_bank_balance=balances.total,
        )
        return OwnerDashboard(
            mode=mode,
            date_from=d_from,
            date_to=d_to,
            today=today,
            kpis=kpis,
            balances=balances,
            missing=missing,
            alerts=self._alerts(today, missing),
            branches=self._branch_rows(d_from, d_to, ho_by_branch, missing),
            unallocated_head_office_excl_savings=calc.head_office_excl_savings(
                money(ho_by_branch.get(None, {}).get("total", ZERO)),
                money(ho_by_branch.get(None, {}).get("savings", ZERO)),
            ),
            days=self._days(d_from, d_to, today, missing) if mode == "month" else None,
        )

    def _balances(self, as_of: date) -> BalanceSummary:
        start = self.reports.reporting_start()
        if start is None:
            return BalanceSummary(
                status="not_configured",
                reporting_start=None,
                balance_date=None,
                cash_in_hand=None,
                enbd=None,
                adcb=None,
                pos_pending=None,
                total=None,
            )
        if as_of < start:
            return BalanceSummary(
                status="before_start",
                reporting_start=start,
                balance_date=as_of,
                cash_in_hand=None,
                enbd=None,
                adcb=None,
                pos_pending=None,
                total=None,
            )
        b = BalanceRepository(self.session).balances(as_of)
        return BalanceSummary(
            status="ok",
            reporting_start=start,
            balance_date=b["balance_date"],
            cash_in_hand=money(b["cash_now"]),
            enbd=money(b["enbd_now"]),
            adcb=money(b["adcb_now"]),
            pos_pending=money(b["pos_pending"]),
            total=money(b["total_cash_bank"]),
        )

    def _branch_rows(
        self,
        d_from: date,
        d_to: date,
        ho_by_branch: dict[Any, dict[str, Any]],
        missing: MissingReports,
    ) -> list[BranchRow]:
        sums = self.reports.totals_by_branch(d_from, d_to)
        missing_by = {m.branch_id: m.missing_count for m in missing.branches}
        out: list[BranchRow] = []
        for b in self.reports.branches_for_summary(d_from, d_to):
            s = sums.get(b["branch_id"]) or _zero_sums()
            t = _totals(s)
            h = ho_by_branch.get(b["branch_id"], {"total": ZERO, "savings": ZERO})
            out.append(
                BranchRow(
                    branch_id=b["branch_id"],
                    branch_name=b["branch_name"],
                    report_count=t.report_count,
                    total_sales=t.total_sales,
                    total_orders=t.total_orders,
                    total_received=t.collections.total_received,
                    not_yet_received=t.not_yet_received,
                    shop_expenses_excl_savings=t.shop_expenses_excl_savings,
                    shop_savings=t.shop_savings,
                    head_office_excl_savings=calc.head_office_excl_savings(
                        money(h["total"]), money(h["savings"])
                    ),
                    missing_count=None
                    if missing.status != "ok"
                    else missing_by.get(b["branch_id"], 0),
                )
            )
        return out

    def _days(self, d_from: date, d_to: date, today: date, missing: MissingReports) -> list[DayRow]:
        last = min(d_to, today)
        sums = self.reports.totals_by_day(d_from, last)
        ho = self.head_office.by_day(d_from, last)
        miss_by_day: dict[date, int] = {}
        for mb in missing.branches:
            for d in mb.dates:
                miss_by_day[d] = miss_by_day.get(d, 0) + 1
        rows: list[DayRow] = []
        d = d_from
        while d <= last:
            t = _totals(sums.get(d) or _zero_sums())
            h = ho.get(d, {"total": ZERO, "savings": ZERO})
            h_excl = calc.head_office_excl_savings(money(h["total"]), money(h["savings"]))
            counted = (
                missing.status == "ok"
                and missing.date_from is not None
                and missing.date_from <= d <= (missing.date_to or d)
            )
            rows.append(
                DayRow(
                    date=d,
                    report_count=t.report_count,
                    missing_count=miss_by_day.get(d, 0) if counted else None,
                    total_sales=t.total_sales,
                    total_orders=t.total_orders,
                    total_received=t.collections.total_received,
                    not_yet_received=t.not_yet_received,
                    shop_expenses_excl_savings=t.shop_expenses_excl_savings,
                    head_office_expenses_excl_savings=h_excl,
                    total_savings=calc.total_savings(t.shop_savings, money(h["savings"])),
                    sales_minus_expenses=calc.sales_minus_expenses(
                        t.total_sales, t.shop_expenses_excl_savings, h_excl
                    ),
                )
            )
            d += timedelta(days=1)
        return rows

    def _alerts(self, today: date, missing: MissingReports) -> list[Alert]:
        c = AlertRepository(self.session).counts(today)
        out: list[Alert] = []

        def add(
            key: str,
            title: str,
            count: int,
            severity: Literal["warning", "danger", "info"],
            detail: str | None = None,
        ) -> None:
            if count > 0:
                out.append(
                    Alert(
                        key=key,
                        title=title,
                        count=count,
                        severity=severity,
                        detail=detail,
                        href=ALERT_LINKS.get(key),
                    )
                )

        add("missing_reports", "Missing daily reports", missing.missing_count, "warning")
        add("visas_30", "Visas expiring within 30 days", int(c["visas_30"]), "warning")
        add("visas_cancelled", "Visas cancelled by leave", int(c["visas_cancelled"]), "danger")
        add(
            "leave_limit_30",
            "Staff within 30 days of the 6-month leave limit",
            int(c["leave_limit_30"]),
            "warning",
        )
        add("passports_30", "Passports expiring within 30 days", int(c["passports_30"]), "warning")
        add("tasks_overdue", "Overdue tasks", int(c["tasks_overdue"]), "warning")
        add("tasks_due_today", "Tasks due today", int(c["tasks_due_today"]), "warning")
        add("tasks_due_7", "Tasks due within the next 7 days", int(c["tasks_due_7"]), "info")
        add(
            "licenses_30",
            "Trade licences expiring within 30 days",
            int(c["licenses_30"]),
            "warning",
        )
        add(
            "licenses_renewal_90",
            "Trade licence renewals due in 31 to 90 days",
            int(c["licenses_renewal_90"]),
            "warning",
        )
        add(
            "rentals_ending_30",
            "Rental agreements ending within 30 days",
            int(c["rentals_ending_30"]),
            "warning",
        )
        add(
            "rentals_renewal_90",
            "Rental renewals due in 31 to 90 days",
            int(c["rentals_renewal_90"]),
            "warning",
        )
        add(
            "rentals_expired",
            "Rental agreements ended and not renewed",
            int(c["rentals_expired"]),
            "danger",
        )
        add(
            "cheques_bounced",
            "Bounced cheques without a replacement",
            int(c["cheques_bounced"]),
            "danger",
        )
        add("pdc_overdue", "Overdue PDC cheques", int(c["pdc_overdue"]), "danger")
        add("pdc_due_7", "PDC cheques due within 7 days", int(c["pdc_due_7"]), "warning")
        add("pdc_due_30", "PDC cheques due in 8 to 30 days", int(c["pdc_due_30"]), "warning")
        add(
            "suppliers_owed",
            "Amount owed to suppliers",
            int(c["suppliers_owed"]),
            "info",
            detail=str(money(c["suppliers_owed_total"])),
        )
        return out


def _zero_sums() -> dict[str, Any]:
    return {
        k: ZERO
        for k in (
            "total_sales",
            "cash_received",
            "pos_amount",
            "bank_transfer",
            "link_payment",
            "shop_expenses",
            "shop_savings",
        )
    } | {"report_count": 0, "total_orders": 0}
