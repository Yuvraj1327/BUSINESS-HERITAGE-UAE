"""Reports & Analytics (Step 12).

Nothing here owns a business rule. Every figure comes from the code that already owns it:
* Step 7 daily-report sums and formulas   -> repositories.report_repository + core.calculations (+ dashboard `_totals`)
* Step 8 / 10 ledger, balances, suppliers -> FinanceRepository / CashBankService (app_cash_bank_ledger, app_balances,
                                             v_supplier_outstanding)
* Step 9 employees and licences           -> HrRepository + hr_core.employee_dict / license_dict
* Step 10 rentals and PDC cheques         -> RentalRepository
* Step 11 tasks                           -> core.tasks + TaskRepository rules (open task past due = overdue)
Each report is built ONCE as a `Table`; the screen, the CSV and the Excel export all read that same table, so exported
totals cannot differ from what is shown."""

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any

from sqlalchemy.orm import Session

from app.core import calculations as calc
from app.core.calculations import ZERO, money
from app.core.exceptions import NotFoundError, UnprocessableError
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.hr_repository import HrRepository
from app.repositories.rental_repository import RentalRepository
from app.schemas.analytics import (
    AppliedFilters,
    Chart,
    ChartPoint,
    ChartSet,
    ColumnKind,
    Overview,
    OverviewKpis,
    Period,
    ReportCatalogItem,
    ReportColumn,
    ReportOut,
    SummaryItem,
)
from app.services.base import BaseService
from app.services.cash_bank_service import ACCOUNTS, CashBankService
from app.services.dashboard_service import DashboardService, _totals
from app.services.hr_core import employee_dict, license_dict
from app.utils.time import BUSINESS_TZ, dubai_today

logger = logging.getLogger(__name__)

MAX_RANGE_DAYS = 366
MAX_EXPORT_ROWS = 100_000
ALL_ROWS = 1_000_000
Row = dict[str, Any]

SUM_KEYS = (
    "report_count", "total_sales", "total_orders", "cash_received", "pos_amount", "bank_transfer",
    "link_payment", "shop_expenses", "shop_savings",
)  # fmt: skip


@dataclass(frozen=True)
class RF:
    """Validated report filters."""

    d_from: date
    d_to: date
    period: Period = "day"
    branch_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    account: str | None = None
    kind: str | None = None
    module: str | None = None
    action: str | None = None
    actor_id: uuid.UUID | None = None
    # Activity history only: 'user' = done by a signed-in ERP user, 'system' = no signed-in user (setup / operator).
    source: str | None = None
    q: str | None = None
    page: int = 1
    page_size: int = 25
    export: bool = False


@dataclass
class Table:
    key: str
    columns: list[ReportColumn]
    rows: list[Row]
    summary: list[SummaryItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    total: int | None = None  # set only when the rows are already one page (activity history)
    paged: bool = False


def C(key: str, label: str, kind: ColumnKind = "text") -> ReportColumn:
    return ReportColumn(key=key, label=label, kind=kind)


def S(label: str, value: Any, kind: ColumnKind = "money") -> SummaryItem:
    return SummaryItem(label=label, value=value, kind=kind)


# key -> (category, title, description)
CATALOG: dict[str, tuple[str, str, str]] = {
    "sales_trend": ("Sales", "Sales trend", "Sales, reported orders and average sale per order for each day, week, month or year."),
    "sales_by_branch": ("Sales", "Sales by branch", "Sales and reported orders for each branch."),
    "collections_trend": ("Collections", "Collections by date", "Cash, POS, bank transfer and payment link collections for each period."),
    "collections_by_branch": ("Collections", "Collections by branch", "Collection breakdown for each branch."),
    "reconciliation_by_branch": ("Reconciliation", "Reconciliation by branch", "Total sales against total collections for each branch (Step 7 formulas)."),
    "reconciliation_by_date": ("Reconciliation", "Reconciliation history", "Total sales against total collections for each period."),
    "shop_expenses_by_branch": ("Expenses & Savings", "Shop expenses by branch", "Shop expenses, shop savings and expenses excluding savings."),
    "shop_expenses_by_date": ("Expenses & Savings", "Shop expenses by date", "Shop expenses, savings and expenses excluding savings for each period."),
    "ho_expenses": ("Expenses & Savings", "Head office expense history", "Every head office expense in the period."),
    "ho_by_category": ("Expenses & Savings", "Head office expenses by category", "Totals per expense category, savings shown separately."),
    "ho_by_source": ("Expenses & Savings", "Head office expenses by payment source", "Totals paid from Cash, ENBD or ADCB."),
    "ho_by_branch": ("Expenses & Savings", "Head office expenses by branch", "Totals per branch or All Branches."),
    "savings": ("Expenses & Savings", "Savings summary", "Savings brought forward, shop savings, head office savings and total savings."),
    "cash_accounts": ("Cash & Banks", "Account balances and movements", "Opening, incoming, outgoing and closing balance for Cash, ENBD, ADCB and POS Pending."),
    "branch_cash": ("Cash & Banks", "Branch cash balances", "Cash held by each branch at the end of the period."),
    "ledger": ("Cash & Banks", "Account transaction history", "Every cash and bank movement with a running balance per account."),
    "supplier_balances": ("Suppliers", "Supplier balances", "Opening dues, new dues, payments and outstanding balance per supplier."),
    "supplier_payments": ("Suppliers", "Supplier dues and payments", "Every supplier due and payment in the period."),
    "employees": ("Employees & Compliance", "Employees", "Employee status, branch and monthly salary. Owner only."),
    "employees_by_branch": ("Employees & Compliance", "Employees by branch", "Employee counts and payroll per branch. Owner only."),
    "visas_passports": ("Employees & Compliance", "Visas and passports", "Every visa and passport expiry with its status."),
    "leave_cases": ("Employees & Compliance", "Six-month leave rule cases", "Employees on leave or with a leave-cancelled visa."),
    "licenses": ("Employees & Compliance", "Trade licences", "Licence expiry status, renewal fees and renewals."),
    "license_renewals": ("Employees & Compliance", "Trade licence renewal history", "Renewals recorded in the period."),
    "rentals": ("Rentals & PDC", "Rental agreements", "Agreements with status, end date and annual rent."),
    "rentals_by_branch": ("Rentals & PDC", "Annual rent by branch", "Active agreements and annual rent per branch."),
    "rental_renewals": ("Rentals & PDC", "Agreement renewal history", "Agreements created as renewals of an earlier agreement."),
    "pdc_summary": ("Rentals & PDC", "PDC cheque status summary", "Pending, overdue, upcoming, cleared and bounced cheques by bank."),
    "pdc_by_branch": ("Rentals & PDC", "PDC cheques by branch", "Pending, cleared and bounced cheque amounts per branch."),
    "pdc_cheques": ("Rentals & PDC", "PDC cheques", "Cheques dated inside the period with their status."),
    "pdc_clearance": ("Rentals & PDC", "Cheque clearance history", "Cheques cleared in the period."),
    "tasks_by_branch": ("Tasks & Reporting", "Task summary by branch", "Task counts by status and overdue tasks per branch."),
    "tasks_completed": ("Tasks & Reporting", "Task completion history", "Tasks completed in the period."),
    "missing_by_branch": ("Tasks & Reporting", "Reporting compliance by branch", "Daily reports expected, submitted and missing per branch."),
    "missing_by_date": ("Tasks & Reporting", "Missing report history", "Branches missing a daily report on each date."),
    "activity": ("Activity", "Activity history", "Who changed what and when, from the append-only audit log. Owner only."),
}  # fmt: skip

# Activity history: audit table -> (module label, label column used to name the record)
ACTIVITY_MODULES: dict[str, tuple[str, str]] = {
    "daily_reports": ("Daily Reports", "report_date"),
    "head_office_expenses": ("Expenses & Savings", "note"),
    "supplier_entries": ("Suppliers", "reference"),
    "suppliers": ("Suppliers", "name"),
    "cash_transfers": ("Cash & Banks", "note"),
    "pos_settlements": ("Cash & Banks", "reference"),
    "opening_balances": ("Opening Balances", "as_of_date"),
    "opening_branch_cash": ("Opening Balances", "branch_id"),
    "employees": ("Employees", "full_name"),
    "trade_licenses": ("Trade Licenses", "license_no"),
    "rental_agreements": ("Rental Agreements", "landlord"),
    "pdc_cheques": ("PDC Cheques", "cheque_no"),
    "tasks": ("Tasks", "title"),
    "profiles": ("User Management", "full_name"),
    "branches": ("Branch Management", "name"),
    "orders": ("Orders", "order_no"),
    "order_payments": ("Order Payments", "amount"),
    "customers": ("Customers", "name"),
}
MODULE_KEYS = {
    "daily_reports": ["daily_reports"],
    "expenses": ["head_office_expenses"],
    "suppliers": ["suppliers", "supplier_entries"],
    "cash_banks": ["cash_transfers", "pos_settlements"],
    "opening_balances": ["opening_balances", "opening_branch_cash"],
    "employees": ["employees"],
    "trade_licenses": ["trade_licenses"],
    "rentals": ["rental_agreements"],
    "pdc_cheques": ["pdc_cheques"],
    "tasks": ["tasks"],
    "users": ["profiles"],
    "branches": ["branches"],
    "orders": ["orders", "order_payments"],
    "customers": ["customers"],
}
HIDDEN_FIELDS = {
    "id", "created_at", "created_by", "updated_at", "updated_by", "client_key", "voided_by", "completed_by",
}  # fmt: skip
SECRET_WORDS = ("password", "token", "secret", "api_key", "service_role")


def _blocked(k: str) -> bool:
    low = k.lower()
    return k in HIDDEN_FIELDS or any(w in low for w in SECRET_WORDS)


def _show(v: Any) -> str:
    return "—" if v is None or v == "" else str(v)


ACTION_LABELS = {
    "INSERT": "Created",
    "UPDATE": "Updated",
    "DELETE": "Deleted",
    "ACCESS_DENIED": "Access denied",
}


def change_summary(action: str, old: dict | None, new: dict | None) -> str:
    """Field-level summary. Hidden bookkeeping columns and anything secret-looking are never shown."""
    if action == "INSERT":
        return "Record created"
    if action == "DELETE":
        return "Record deleted"
    if action not in ("UPDATE",):
        return ACTION_LABELS.get(action, "Recorded")
    o, n = old or {}, new or {}
    parts = [
        f"{k.replace('_', ' ').capitalize()}: {_show(o.get(k))} → {_show(n.get(k))}"
        for k in n
        if not _blocked(k) and o.get(k) != n.get(k)
    ]
    return "; ".join(parts) or "No visible change"


# Tables whose INSERTs with no signed-in user are the one-time bootstrap: the branch seed (migration 0009) and the
# first Owner profile created by an operator in the SQL editor / provisioning script.
BOOTSTRAP_TABLES = {"branches", "profiles"}
SYSTEM_SETUP_LABEL = "System / Initial Setup"
SYSTEM_OTHER_LABEL = "System (no signed-in user)"
UNKNOWN_USER_LABEL = "Unknown user"


def actor_label(actor_id: Any, actor_name: str | None, table: str, action: str) -> tuple[str, str]:
    """(display name, source). The database records auth.uid(); a NULL actor means no signed-in ERP user."""
    if actor_id is None:
        if action == "INSERT" and table in BOOTSTRAP_TABLES:
            return SYSTEM_SETUP_LABEL, "System"
        return SYSTEM_OTHER_LABEL, "System"
    return (actor_name or UNKNOWN_USER_LABEL), "User"


def record_label(table: str, old: dict | None, new: dict | None) -> str:
    col = ACTIVITY_MODULES.get(table, ("", "id"))[1]
    src = new or old or {}
    v = src.get(col)
    return str(v) if v not in (None, "") else ""


def _bucket(d: date, period: Period) -> str:
    if period == "week":
        return f"Week of {(d - timedelta(days=d.weekday())).isoformat()}"
    if period == "month":
        return d.strftime("%Y-%m")
    if period == "year":
        return str(d.year)
    return d.isoformat()


def _add(a: Row, b: Row) -> Row:
    return {k: (a.get(k, 0) or 0) + (b.get(k, 0) or 0) for k in SUM_KEYS}


def _zero() -> Row:
    return {k: 0 for k in SUM_KEYS}


def _amount(items: list[Row], buckets: dict[str, Callable[[Row], bool]], label: str) -> Decimal:
    return money(sum((c["amount"] for c in items if buckets[label](c)), ZERO))


def _pct(n: int, d: int) -> Decimal | None:
    return None if d == 0 else (Decimal(n) * 100 / Decimal(d)).quantize(Decimal("0.1"))


class AnalyticsService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.dash = DashboardService(session)
        self.reports = self.dash.reports
        self.ho = self.dash.head_office
        self.repo = AnalyticsRepository(session)
        self.cash = CashBankService(session)
        self.fin = self.cash.fin
        self.hr = HrRepository(session)
        self.rent = RentalRepository(session)
        self.today = dubai_today()
        self._memo: dict[Any, Any] = {}
        self._branch_names: dict[uuid.UUID, str] | None = None

    # ---- filters -----------------------------------------------------------------------------------------
    def validate(self, rf: RF) -> RF:
        if rf.d_from > rf.d_to:
            raise UnprocessableError(
                "Start date is after end date",
                fields={"date_from": ["Start date must not be after end date"]},
            )
        if rf.d_to > self.today:
            raise UnprocessableError(
                "End date cannot be in the future",
                fields={"date_to": ["End date cannot be after today (Dubai)"]},
            )
        if (rf.d_to - rf.d_from).days + 1 > MAX_RANGE_DAYS:
            raise UnprocessableError(
                f"Choose at most {MAX_RANGE_DAYS} days",
                fields={"date_from": [f"Choose at most {MAX_RANGE_DAYS} days"]},
            )
        if rf.branch_id is not None and self.reports.get_branch(rf.branch_id) is None:
            raise UnprocessableError("Unknown branch", fields={"branch_id": ["Branch not found"]})
        if rf.account is not None and rf.account not in ACCOUNTS:
            raise UnprocessableError(
                "Unknown account", fields={"account": ["Choose a listed account"]}
            )
        if rf.module is not None and rf.module not in MODULE_KEYS:
            raise UnprocessableError(
                "Unknown module", fields={"module": ["Choose a listed module"]}
            )
        return rf

    def applied(self, rf: RF) -> AppliedFilters:
        name = "All Branches"
        if rf.branch_id is not None:
            b = self.reports.get_branch(rf.branch_id)
            name = b["name"] if b else "Unknown"
        return AppliedFilters(
            date_from=rf.d_from, date_to=rf.d_to, period=rf.period, branch_id=rf.branch_id,
            branch_name=name, supplier_id=rf.supplier_id, account=rf.account,
        )  # fmt: skip

    def catalog(self) -> list[ReportCatalogItem]:
        return [
            ReportCatalogItem(key=k, category=v[0], title=v[1], description=v[2])
            for k, v in CATALOG.items()
        ]

    # ---- shared sources (memoised for one request) --------------------------------------------------------
    def names(self, rf: RF) -> list[Row]:
        k = ("names", rf.d_from, rf.d_to)
        if k not in self._memo:
            self._memo[k] = self.reports.branches_for_summary(rf.d_from, rf.d_to)
        return self._memo[k]  # type: ignore[no-any-return]

    def daily(self, rf: RF) -> dict[date, Row]:
        k = ("daily", rf.branch_id, rf.d_from, rf.d_to)
        if k not in self._memo:
            self._memo[k] = self.repo.daily_by_day(rf.branch_id, rf.d_from, rf.d_to)
        return self._memo[k]  # type: ignore[no-any-return]

    def by_branch(self, rf: RF) -> list[tuple[Row, Row]]:
        """[(branch row, sums)] for every branch shown (one branch when filtered)."""
        sums = self.reports.totals_by_branch(rf.d_from, rf.d_to)
        out = []
        for b in self.names(rf):
            if rf.branch_id is not None and b["branch_id"] != rf.branch_id:
                continue
            out.append((b, sums.get(b["branch_id"]) or _zero()))
        return out

    def grouped(self, rf: RF) -> list[tuple[str, Row]]:
        acc: dict[str, Row] = {}
        for d, s in sorted(self.daily(rf).items()):
            key = _bucket(d, rf.period)
            acc[key] = _add(acc[key], s) if key in acc else _add(_zero(), s)
        return list(acc.items())

    def ho_totals(self, rf: RF) -> tuple[Decimal, Decimal]:
        rows = self.ho.by_branch(rf.d_from, rf.d_to)
        total = savings = ZERO
        for b, r in rows.items():
            if rf.branch_id is None or b == rf.branch_id:
                total += r["total"]
                savings += r["savings"]
        return money(total), money(savings)

    def tracking(self, rf: RF) -> tuple[date, date] | None:
        start = self.cash.tracking_start()
        if start is None or rf.d_to < start:
            return None
        return max(rf.d_from, start), rf.d_to

    # ---- overview ----------------------------------------------------------------------------------------
    def overview(self, rf: RF) -> Overview:
        rf = self.validate(rf)
        t = _totals(self.reports.totals(rf.branch_id, rf.d_from, rf.d_to))
        ho_total, ho_savings = self.ho_totals(rf)
        ho_excl = calc.head_office_excl_savings(ho_total, ho_savings)
        bal = self.dash._balances(min(rf.d_to, self.today))
        notes = [
            "Cash + Bank Balance is the company-wide balance at the end date; it is not filtered by branch.",
            "Savings are excluded from expenses; Total Savings = shop savings + head office savings in the period.",
        ]
        if rf.branch_id is not None:
            notes.append(
                "Head office expenses are those recorded against the selected branch (not All Branches)."
            )
        return Overview(
            filters=self.applied(rf),
            kpis=OverviewKpis(
                total_sales=t.total_sales,
                total_collections=t.collections.total_received,
                total_orders=t.total_orders,
                shop_expenses=t.shop_expenses_excl_savings,
                head_office_expenses=ho_excl,
                total_savings=calc.total_savings(t.shop_savings, ho_savings),
                sales_minus_expenses=calc.sales_minus_expenses(
                    t.total_sales, t.shop_expenses_excl_savings, ho_excl
                ),
                cash_bank_balance=bal.total,
                not_yet_received=t.not_yet_received,
                balance_status=bal.status,
                balance_date=bal.balance_date,
            ),
            notes=notes,
            generated_at=datetime.now(BUSINESS_TZ),
        )

    # ---- sales / collections / reconciliation -------------------------------------------------------------
    def sales_trend(self, rf: RF) -> Table:
        rows, tot_s, tot_o, tot_r = [], ZERO, 0, 0
        for label, s in self.grouped(rf):
            t = _totals(s)
            rows.append({
                "period": label, "reports": t.report_count, "orders": t.total_orders, "sales": t.total_sales,
                "avg_order": money(t.total_sales / t.total_orders) if t.total_orders else None,
            })  # fmt: skip
            tot_s, tot_o, tot_r = (
                tot_s + t.total_sales,
                tot_o + t.total_orders,
                tot_r + t.report_count,
            )
        return Table(
            "sales_trend",
            [C("period", "Period"), C("reports", "Daily reports", "int"), C("orders", "Orders", "int"),
             C("sales", "Sales (AED)", "money"), C("avg_order", "Average sale per order (AED)", "money")],
            rows,
            [S("Total sales (AED)", money(tot_s)), S("Orders reported", tot_o, "int"),
             S("Average sale per order (AED)", money(tot_s / tot_o) if tot_o else None),
             S("Daily reports", tot_r, "int")],
            ["Average sale per order is only shown where orders were reported."],
        )  # fmt: skip

    def sales_by_branch(self, rf: RF) -> Table:
        rows, tot_s, tot_o = [], ZERO, 0
        for b, s in self.by_branch(rf):
            t = _totals(s)
            rows.append({
                "branch": b["branch_name"], "reports": t.report_count, "orders": t.total_orders,
                "sales": t.total_sales,
                "avg_order": money(t.total_sales / t.total_orders) if t.total_orders else None,
            })  # fmt: skip
            tot_s, tot_o = tot_s + t.total_sales, tot_o + t.total_orders
        return Table(
            "sales_by_branch",
            [C("branch", "Branch"), C("reports", "Daily reports", "int"), C("orders", "Orders", "int"),
             C("sales", "Sales (AED)", "money"), C("avg_order", "Average sale per order (AED)", "money")],
            rows,
            [S("Total sales (AED)", money(tot_s)), S("Orders reported", tot_o, "int")],
        )  # fmt: skip

    def _coll_row(self, label_key: str, label: str, s: Row) -> Row:
        t = _totals(s)
        c = t.collections
        return {label_key: label, "cash": c.cash_received, "pos": c.pos_amount, "bank": c.bank_transfer,
                "link": c.link_payment, "total": c.total_received}  # fmt: skip

    def _coll_table(self, key: str, first: ReportColumn, rows: list[Row]) -> Table:
        sums = {
            k: money(sum((r[k] for r in rows), ZERO))
            for k in ("cash", "pos", "bank", "link", "total")
        }
        return Table(
            key,
            [first, C("cash", "Cash received (AED)", "money"), C("pos", "POS received (AED)", "money"),
             C("bank", "Bank transfers (AED)", "money"), C("link", "Payment links (AED)", "money"),
             C("total", "Total collections (AED)", "money")],
            rows,
            [S("Total collections (AED)", sums["total"]), S("Cash received (AED)", sums["cash"]),
             S("POS received (AED)", sums["pos"]), S("Bank transfers (AED)", sums["bank"]),
             S("Payment links (AED)", sums["link"])],
        )  # fmt: skip

    def collections_trend(self, rf: RF) -> Table:
        rows = [self._coll_row("period", lbl, s) for lbl, s in self.grouped(rf)]
        return self._coll_table("collections_trend", C("period", "Period"), rows)

    def collections_by_branch(self, rf: RF) -> Table:
        rows = [self._coll_row("branch", b["branch_name"], s) for b, s in self.by_branch(rf)]
        return self._coll_table("collections_by_branch", C("branch", "Branch"), rows)

    def _recon_row(self, key: str, label: str, s: Row) -> Row:
        t = _totals(s)
        diff = calc.difference(t.total_sales, t.collections.total_received)
        return {key: label, "sales": t.total_sales, "collections": t.collections.total_received,
                "difference": diff, "not_yet_received": t.not_yet_received,
                "status": calc.check_label(diff)}  # fmt: skip

    def _recon_table(self, key: str, first: ReportColumn, rows: list[Row]) -> Table:
        sales = money(sum((r["sales"] for r in rows), ZERO))
        coll = money(sum((r["collections"] for r in rows), ZERO))
        return Table(
            key,
            [first, C("sales", "Total sales (AED)", "money"), C("collections", "Total collections (AED)", "money"),
             C("difference", "Difference (AED)", "money"), C("not_yet_received", "Not yet received (AED)", "money"),
             C("status", "Status")],
            rows,
            [S("Total sales (AED)", sales), S("Total collections (AED)", coll),
             S("Difference (AED)", calc.difference(sales, coll)),
             S("Not yet received (AED)", calc.not_yet_received(sales, coll))],
            ["Difference = total sales - total collections. 'Matches' when it is exactly zero (Step 7 rule)."],
        )  # fmt: skip

    def reconciliation_by_branch(self, rf: RF) -> Table:
        rows = [self._recon_row("branch", b["branch_name"], s) for b, s in self.by_branch(rf)]
        return self._recon_table("reconciliation_by_branch", C("branch", "Branch"), rows)

    def reconciliation_by_date(self, rf: RF) -> Table:
        rows = [self._recon_row("period", lbl, s) for lbl, s in self.grouped(rf)]
        return self._recon_table("reconciliation_by_date", C("period", "Period"), rows)

    # ---- expenses and savings ----------------------------------------------------------------------------
    def _shop_table(self, key: str, first: ReportColumn, items: list[tuple[str, Row]]) -> Table:
        rows: list[Row] = []
        for label, s in items:
            t = _totals(s)
            rows.append({"label": label, "expenses": t.shop_expenses, "savings": t.shop_savings,
                         "excl": t.shop_expenses_excl_savings})  # fmt: skip
        exp = money(sum((r["expenses"] for r in rows), ZERO))
        sav = money(sum((r["savings"] for r in rows), ZERO))
        return Table(
            key,
            [first, C("expenses", "Shop expenses (AED)", "money"), C("savings", "Shop savings (AED)", "money"),
             C("excl", "Shop expenses excluding savings (AED)", "money")],
            rows,
            [S("Total shop expenses (AED)", exp), S("Shop savings (AED)", sav),
             S("Expenses excluding savings (AED)", calc.shop_expenses_excl_savings(exp, sav))],
            ["Savings are excluded from normal expenses (approved rule)."],
        )  # fmt: skip

    def shop_expenses_by_branch(self, rf: RF) -> Table:
        return self._shop_table(
            "shop_expenses_by_branch", C("label", "Branch"),
            [(b["branch_name"], s) for b, s in self.by_branch(rf)],
        )  # fmt: skip

    def shop_expenses_by_date(self, rf: RF) -> Table:
        return self._shop_table("shop_expenses_by_date", C("label", "Period"), self.grouped(rf))

    def ho_expenses(self, rf: RF) -> Table:
        rows = self.repo.ho_list(rf.branch_id, rf.d_from, rf.d_to)
        total = money(sum((r["amount"] for r in rows), ZERO))
        sav = money(sum((r["amount"] for r in rows if r["is_saving"]), ZERO))
        for r in rows:
            r["type"] = "Saving" if r["is_saving"] else "Expense"
        return Table(
            "ho_expenses",
            [C("expense_date", "Date", "date"), C("category", "Category"), C("branch_name", "Branch"),
             C("paid_from", "Paid from"), C("type", "Type"), C("amount", "Amount (AED)", "money"),
             C("note", "Note"), C("created_by_name", "Entered by")],
            rows,
            [S("Total head office (AED)", total), S("Marked as saving (AED)", sav),
             S("Excluding savings (AED)", calc.head_office_excl_savings(total, sav)),
             S("Entries", len(rows), "int")],
        )  # fmt: skip

    def _ho_group(self, key: str, group: str, label: str, rf: RF) -> Table:
        rows = []
        for r in self.repo.ho_grouped(group, rf.branch_id, rf.d_from, rf.d_to):
            tot, sav = money(r["total"]), money(r["savings"])
            rows.append({"label": r["label"], "count": int(r["cnt"]), "total": tot, "savings": sav,
                         "excl": calc.head_office_excl_savings(tot, sav)})  # fmt: skip
        total = money(sum((r["total"] for r in rows), ZERO))
        sav = money(sum((r["savings"] for r in rows), ZERO))
        return Table(
            key,
            [C("label", label), C("count", "Entries", "int"), C("total", "Total (AED)", "money"),
             C("savings", "Marked as saving (AED)", "money"), C("excl", "Excluding savings (AED)", "money")],
            rows,
            [S("Total head office (AED)", total), S("Marked as saving (AED)", sav),
             S("Excluding savings (AED)", calc.head_office_excl_savings(total, sav))],
        )  # fmt: skip

    def ho_by_category(self, rf: RF) -> Table:
        return self._ho_group("ho_by_category", "category", "Category", rf)

    def ho_by_source(self, rf: RF) -> Table:
        return self._ho_group("ho_by_source", "source", "Payment source", rf)

    def ho_by_branch(self, rf: RF) -> Table:
        return self._ho_group("ho_by_branch", "branch", "Branch", rf)

    def savings(self, rf: RF) -> Table:
        t = _totals(self.reports.totals(rf.branch_id, rf.d_from, rf.d_to))
        _, ho_sav = self.ho_totals(rf)
        opening = self.fin.opening()
        brought = money(opening["savings_brought_forward"]) if opening else ZERO
        period = calc.total_savings(t.shop_savings, ho_sav)
        notes = ["Savings are excluded from normal expenses everywhere in the system."]
        rows = [
            {"item": "Savings brought forward (opening balances)", "amount": brought},
            {"item": "Shop savings in the period", "amount": t.shop_savings},
            {"item": "Head office expenses marked as Saving in the period", "amount": ho_sav},
            {"item": "Total savings in the period", "amount": period},
        ]
        start = self.cash.tracking_start()
        if opening is not None and start is not None and rf.d_to >= start:
            rows.append({"item": "Savings position at the end date (all time)",
                         "amount": money(self.fin.balances(rf.d_to)["savings_total"])})  # fmt: skip
        else:
            notes.append(
                "Opening balances are not configured or the period is before the tracking start."
            )
        return Table(
            "savings", [C("item", "Item"), C("amount", "Amount (AED)", "money")], rows,
            [S("Total savings in the period (AED)", period)], notes,
        )  # fmt: skip

    # ---- cash and banks ----------------------------------------------------------------------------------
    def _no_ledger(self, key: str, cols: list[ReportColumn]) -> Table:
        return Table(key, cols, [], notes=[
            "Opening balances are not configured, or the selected period ends before the tracking start."])  # fmt: skip

    def cash_accounts(self, rf: RF) -> Table:
        cols = [C("account", "Account"), C("opening", "Opening balance (AED)", "money"),
                C("incoming", "Incoming (AED)", "money"), C("outgoing", "Outgoing (AED)", "money"),
                C("closing", "Closing balance (AED)", "money")]  # fmt: skip
        rng = self.tracking(rf)
        if rng is None:
            return self._no_ledger("cash_accounts", cols)
        rep = self.cash.accounts(*rng)
        rows = [a.model_dump() for a in rep.accounts]
        cash_bank = [r for r in rows if r["account"] != "POS Pending"]
        notes = [
            "POS Pending is money owed by the card provider; it is not part of Cash + Bank until settled."
        ]
        if rng[0] != rf.d_from:
            notes.append(f"The period starts at the tracking start ({rng[0].isoformat()}).")
        return Table(
            "cash_accounts", cols, rows,
            [S("Cash + Bank closing (AED)", money(sum((r["closing"] for r in cash_bank), ZERO))),
             S("Cash + Bank incoming (AED)", money(sum((r["incoming"] for r in cash_bank), ZERO))),
             S("Cash + Bank outgoing (AED)", money(sum((r["outgoing"] for r in cash_bank), ZERO)))],
            notes,
        )  # fmt: skip

    def branch_cash(self, rf: RF) -> Table:
        cols = [C("branch_name", "Branch"), C("opening", "Opening (AED)", "money"),
                C("incoming", "Incoming (AED)", "money"), C("outgoing", "Outgoing (AED)", "money"),
                C("closing", "Cash balance (AED)", "money")]  # fmt: skip
        if self.tracking(rf) is None:
            return self._no_ledger("branch_cash", cols)
        rep = self.cash.branches(rf.d_to)
        rows = [r.model_dump() for r in rep.rows if rf.branch_id in (None, r.branch_id)]
        return Table(
            "branch_cash", cols, rows,
            [S("Total branch cash (AED)", money(sum((r["closing"] for r in rows), ZERO)))],
            [f"Balances are as at {rf.d_to.isoformat()}; the opening column is the balance when tracking began."],
        )  # fmt: skip

    LEDGER_KINDS = {
        "transfers": "cash_transfers",
        "pos_settlements": "pos_settlements",
        "rental_cheques": "pdc_cheques",
        "daily_reports": "daily_reports",
        "expenses": "head_office_expenses",
    }

    def ledger(self, rf: RF) -> Table:
        cols = [C("txn_date", "Date", "date"), C("account", "Account"), C("txn_type", "Transaction type"),
                C("description", "Reference"), C("branch_name", "Branch"),
                C("incoming", "Incoming (AED)", "money"), C("outgoing", "Outgoing (AED)", "money"),
                C("balance", "Balance (AED)", "money")]  # fmt: skip
        rng = self.tracking(rf)
        if rng is None:
            return self._no_ledger("ledger", cols)
        if rf.kind is not None and rf.kind not in self.LEDGER_KINDS:
            raise UnprocessableError(
                "Unknown kind", fields={"kind": ["Choose a listed transaction kind"]}
            )
        rep = self.cash.accounts(*rng)
        running = {a.account: a.opening for a in rep.accounts}
        rows_db, _, _ = self.fin.ledger_page(rng[0], rng[1], None, None, None, ALL_ROWS, 0)
        rows_db.sort(key=lambda r: (r["txn_date"], r["created_at"], r["txn_type"]))
        out: list[Row] = []
        for r in (
            rows_db
        ):  # balances are per ACCOUNT over every movement; filters only hide rows afterwards
            amt = money(r["amount"])
            running[r["account"]] = money(running.get(r["account"], ZERO) + amt)
            if rf.account and r["account"] != rf.account:
                continue
            if rf.branch_id and r["branch_id"] != rf.branch_id:
                continue
            if rf.kind and r["source_table"] != self.LEDGER_KINDS[rf.kind]:
                continue
            out.append({
                "txn_date": r["txn_date"], "account": r["account"], "txn_type": r["txn_type"],
                "description": r["description"], "branch_name": r["branch_name"] or "",
                "incoming": amt if amt > 0 else ZERO, "outgoing": -amt if amt < 0 else ZERO,
                "balance": running[r["account"]],
            })  # fmt: skip
        inc = money(sum((r["incoming"] for r in out), ZERO))
        outg = money(sum((r["outgoing"] for r in out), ZERO))
        return Table(
            "ledger", cols, out,
            [S("Incoming (AED)", inc), S("Outgoing (AED)", outg), S("Net movement (AED)", money(inc - outg)),
             S("Transactions", len(out), "int")],
            ["Each row is counted once: balances come from the same ledger as Cash & Banks and the dashboard.",
             "Balance is the running balance of that account after the transaction."],
        )  # fmt: skip

    # ---- suppliers ---------------------------------------------------------------------------------------
    def supplier_balances(self, rf: RF) -> Table:
        rows = []
        for r in self.repo.supplier_period(rf.supplier_id, rf.d_from, rf.d_to):
            owed_ever = money(r["opening_outstanding"] + r["dues_all"])
            outstanding = money(r["outstanding"])
            if outstanding <= 0 and owed_ever > 0:
                status = "Fully paid"
            elif r["paid_all"] > 0 and outstanding > 0:
                status = "Partially paid"
            elif outstanding > 0:
                status = "Unpaid"
            else:
                status = "No dues"
            rows.append({
                "supplier": r["name"], "category": r["category"] or "", "active": "Active" if r["is_active"] else "Inactive",
                "opening": money(r["opening_outstanding"]), "dues_period": money(r["dues_period"]),
                "paid_period": money(r["paid_period"]), "payments": int(r["pay_count"]),
                "paid_all": money(r["paid_all"]), "outstanding": outstanding, "status": status,
            })  # fmt: skip
        by_status: dict[str, int] = defaultdict(int)
        for r in rows:
            by_status[r["status"]] += 1
        return Table(
            "supplier_balances",
            [C("supplier", "Supplier"), C("category", "Category"), C("active", "Status"),
             C("opening", "Opening dues (AED)", "money"), C("dues_period", "New dues in period (AED)", "money"),
             C("paid_period", "Paid in period (AED)", "money"), C("payments", "Payments in period", "int"),
             C("paid_all", "Total paid, all time (AED)", "money"), C("outstanding", "Outstanding (AED)", "money"),
             C("status", "Payment status")],
            rows,
            [S("Total suppliers", len(rows), "int"),
             S("Total outstanding dues (AED)", money(sum((r["outstanding"] for r in rows), ZERO))),
             S("Total payments made, all time (AED)", money(sum((r["paid_all"] for r in rows), ZERO))),
             S("Payments made in period (AED)", money(sum((r["paid_period"] for r in rows), ZERO))),
             S("Fully paid", by_status["Fully paid"], "int"), S("Partially paid", by_status["Partially paid"], "int"),
             S("Unpaid", by_status["Unpaid"], "int")],
            ["Outstanding = opening dues + all new dues - all payments (the approved supplier balance); it is a position "
             "as of today. Period columns follow the selected dates."],
        )  # fmt: skip

    def supplier_payments(self, rf: RF) -> Table:
        rows = self.repo.supplier_entries(rf.supplier_id, rf.d_from, rf.d_to)
        for r in rows:
            r["type"] = "Payment" if r["kind"] == "payment" else "Due"
        dues = money(sum((r["amount"] for r in rows if r["kind"] == "due"), ZERO))
        paid = money(sum((r["amount"] for r in rows if r["kind"] == "payment"), ZERO))
        return Table(
            "supplier_payments",
            [C("entry_date", "Date", "date"), C("supplier_name", "Supplier"), C("type", "Type"),
             C("amount", "Amount (AED)", "money"), C("paid_from", "Paid from"), C("branch_name", "Branch"),
             C("reference", "Reference"), C("note", "Note")],
            rows,
            [S("Dues recorded (AED)", dues), S("Payments made (AED)", paid), S("Entries", len(rows), "int")],
        )  # fmt: skip

    # ---- employees and compliance ------------------------------------------------------------------------
    def _employees(self, rf: RF) -> list[Row]:
        k = ("emps", rf.branch_id)
        if k not in self._memo:
            rows, _ = self.hr.employees(
                self.today, None, rf.branch_id, None, False, "name", False, 1, ALL_ROWS
            )
            self._memo[k] = [employee_dict(r, self.today) for r in rows]
        return self._memo[k]  # type: ignore[no-any-return]

    def employees(self, rf: RF) -> Table:
        emps = self._employees(rf)
        rows = [{"name": e["full_name"], "branch": e["branch_name"], "role": e["role_title"] or "",
                 "status": e["status"], "salary": money(e["monthly_salary"]),
                 "payroll": "Yes" if e["payroll_eligible"] else "No"} for e in emps]  # fmt: skip
        payroll = money(sum((e["monthly_salary"] for e in emps if e["payroll_eligible"]), ZERO))
        return Table(
            "employees",
            [C("name", "Employee"), C("branch", "Branch"), C("role", "Role"), C("status", "Status"),
             C("salary", "Monthly salary (AED)", "money"), C("payroll", "In payroll")],
            rows,
            [S("Active employees", sum(1 for e in emps if e["status"] == "Active"), "int"),
             S("Employees on leave", sum(1 for e in emps if e["status"] == "On Leave"), "int"),
             S("Visa cancelled", sum(1 for e in emps if e["status"] == "Visa Cancelled"), "int"),
             S("Monthly payroll (AED)", payroll)],
            ["Payroll = salaries of Active employees only; staff on leave or with a cancelled visa are excluded (D6)."],
        )  # fmt: skip

    def employees_by_branch(self, rf: RF) -> Table:
        acc: dict[str, Row] = {}
        for e in self._employees(rf):
            r = acc.setdefault(e["branch_name"], {"branch": e["branch_name"], "active": 0, "leave": 0,
                                                  "cancelled": 0, "total": 0, "payroll": ZERO})  # fmt: skip
            r["total"] += 1
            r["active"] += e["status"] == "Active"
            r["leave"] += e["status"] == "On Leave"
            r["cancelled"] += e["status"] == "Visa Cancelled"
            if e["payroll_eligible"]:
                r["payroll"] = money(r["payroll"] + e["monthly_salary"])
        rows = sorted(acc.values(), key=lambda r: r["branch"])
        return Table(
            "employees_by_branch",
            [C("branch", "Branch"), C("active", "Active", "int"), C("leave", "On leave", "int"),
             C("cancelled", "Visa cancelled", "int"), C("total", "Total", "int"),
             C("payroll", "Monthly payroll (AED)", "money")],
            rows,
            [S("Employees", sum(r["total"] for r in rows), "int"),
             S("Monthly payroll (AED)", money(sum((r["payroll"] for r in rows), ZERO)))],
        )  # fmt: skip

    def visas_passports(self, rf: RF) -> Table:
        rows: list[Row] = []
        for e in self._employees(rf):
            for doc, exp, state, days in (
                ("Visa", e["visa_expiry"], e["visa_status"], e["visa_days_remaining"]),
                (
                    "Passport",
                    e["passport_expiry"],
                    e["passport_status"],
                    e["passport_days_remaining"],
                ),
            ):
                rows.append({"employee": e["full_name"], "branch": e["branch_name"], "document": doc,
                             "expiry": exp, "status": str(state).replace("_", " ").capitalize(), "days": days})  # fmt: skip
        rows.sort(key=lambda r: (r["expiry"] is None, r["expiry"] or date.max))
        count = lambda doc, st: sum(1 for r in rows if r["document"] == doc and r["status"] == st)  # noqa: E731
        return Table(
            "visas_passports",
            [C("employee", "Employee"), C("branch", "Branch"), C("document", "Document"),
             C("expiry", "Expiry date", "date"), C("status", "Status"), C("days", "Days remaining", "int")],
            rows,
            [S("Expired visas", count("Visa", "Expired"), "int"), S("Visas expiring soon", count("Visa", "Urgent") + count("Visa", "Upcoming"), "int"),
             S("Expired passports", count("Passport", "Expired"), "int"),
             S("Passports expiring soon", count("Passport", "Urgent") + count("Passport", "Upcoming"), "int")],
            ["Status is derived from the actual dates with the Step 9 thresholds. Negative days = already expired."],
        )  # fmt: skip

    def leave_cases(self, rf: RF) -> Table:
        rows = []
        for e in self._employees(rf):
            lv = e["leave"]
            if lv is None and not e["visa_cancelled"]:
                continue
            rows.append({
                "employee": e["full_name"], "branch": e["branch_name"], "status": e["status"],
                "leave_start": lv["leave_start"] if lv else None, "limit_date": lv["limit_date"] if lv else None,
                "days_on_leave": lv["days_on_leave"] if lv else None,
                "days_remaining": lv["days_remaining"] if lv else None,
                "state": str(lv["state"]).replace("_", " ").capitalize() if lv else "Visa cancelled",
            })  # fmt: skip
        return Table(
            "leave_cases",
            [C("employee", "Employee"), C("branch", "Branch"), C("status", "Status"),
             C("leave_start", "Leave start", "date"), C("limit_date", "Six-month limit date", "date"),
             C("days_on_leave", "Days on leave", "int"), C("days_remaining", "Days remaining", "int"),
             C("state", "Rule state")],
            rows,
            [S("Cases", len(rows), "int")],
            ["The limit date is the last allowed day (D24); a visa cancelled by the rule is permanent (D25)."],
        )  # fmt: skip

    def _licenses(self, rf: RF) -> list[Row]:
        rows, _ = self.hr.licenses(
            self.today, None, rf.branch_id, None, False, "expiry", False, 1, ALL_ROWS
        )
        return [license_dict(r, self.today) for r in rows]

    def licenses(self, rf: RF) -> Table:
        lic = self._licenses(rf)
        rows = []
        for item in lic:
            d = item["days_remaining"]
            window = ("Expired" if d < 0 else "Within 30 days" if d <= 30 else "Within 60 days" if d <= 60
                      else "Within 90 days" if d <= 90 else "Later")  # fmt: skip
            rows.append({"branch": item["branch_name"], "license_no": item["license_no"],
                         "authority": item["authority"] or "", "expiry": item["expiry_date"], "days": d,
                         "window": window, "fee": money(item["renewal_fee"]), "renewals": item["renewal_count"],
                         "last_renewed": item["last_renewed_on"]})  # fmt: skip
        n = lambda w: sum(1 for r in rows if r["window"] == w)  # noqa: E731
        due = [r for r in rows if r["window"] != "Later"]
        return Table(
            "licenses",
            [C("branch", "Branch"), C("license_no", "Licence number"), C("authority", "Authority"),
             C("expiry", "Expiry date", "date"), C("days", "Days remaining", "int"), C("window", "Expiry window"),
             C("fee", "Renewal fee (AED)", "money"), C("renewals", "Renewals", "int"),
             C("last_renewed", "Last renewed", "date")],
            rows,
            [S("Active licences", len(rows) - n("Expired"), "int"), S("Expired licences", n("Expired"), "int"),
             S("Expiring within 30 days", n("Within 30 days"), "int"),
             S("Expiring in 31-60 days", n("Within 60 days"), "int"),
             S("Expiring in 61-90 days", n("Within 90 days"), "int"),
             S("Renewal fees due, expired or within 90 days (AED)", money(sum((r["fee"] for r in due), ZERO)))],
        )  # fmt: skip

    def license_renewals(self, rf: RF) -> Table:
        rows = self.repo.license_renewals(rf.branch_id, rf.d_from, rf.d_to)
        return Table(
            "license_renewals",
            [C("renewed_on", "Renewed on", "date"), C("branch_name", "Branch"), C("license_no", "Licence number"),
             C("previous_expiry", "Previous expiry", "date"), C("new_expiry", "New expiry", "date"),
             C("renewal_fee", "Renewal fee (AED)", "money"), C("note", "Note")],
            rows,
            [S("Renewals", len(rows), "int"),
             S("Renewal fees (AED)", money(sum((r["renewal_fee"] for r in rows), ZERO)))],
            ["Renewals post no expense automatically (D28)."],
        )  # fmt: skip

    # ---- rentals and PDC ---------------------------------------------------------------------------------
    def _agreements(self, rf: RF) -> list[Row]:
        k = ("agr", rf.branch_id)
        if k not in self._memo:
            self._memo[k], _ = self.rent.agreements(
                self.today, None, rf.branch_id, None, "end", False, 1, ALL_ROWS
            )
        return self._memo[k]  # type: ignore[no-any-return]

    LIVE = ("Active", "Expiring", "Scheduled")

    def rentals(self, rf: RF) -> Table:
        rows = []
        for a in self._agreements(rf):
            rows.append({"branch": a["branch_name"], "landlord": a["landlord"], "unit": a["unit"] or "",
                         "start": a["start_date"], "end": a["end_date"],
                         "days": (a["end_date"] - self.today).days, "rent": money(a["annual_rent"]),
                         "status": a["display_status"]})  # fmt: skip
        live = [r for r in rows if r["status"] in self.LIVE]
        end_in = lambda n: sum(1 for r in live if 0 <= r["days"] <= n)  # noqa: E731
        return Table(
            "rentals",
            [C("branch", "Branch"), C("landlord", "Landlord"), C("unit", "Unit"), C("start", "Start date", "date"),
             C("end", "End date", "date"), C("days", "Days to end", "int"), C("rent", "Annual rent (AED)", "money"),
             C("status", "Status")],
            rows,
            [S("Active agreements", len(live), "int"), S("Ending within 30 days", end_in(30), "int"),
             S("Ending within 60 days", end_in(60), "int"), S("Ending within 90 days", end_in(90), "int"),
             S("Annual rent, active agreements (AED)", money(sum((r["rent"] for r in live), ZERO)))],
        )  # fmt: skip

    def rentals_by_branch(self, rf: RF) -> Table:
        acc: dict[str, Row] = {}
        for a in self._agreements(rf):
            if a["display_status"] not in self.LIVE:
                continue
            r = acc.setdefault(
                a["branch_name"], {"branch": a["branch_name"], "agreements": 0, "rent": ZERO}
            )
            r["agreements"] += 1
            r["rent"] = money(r["rent"] + a["annual_rent"])
        rows = sorted(acc.values(), key=lambda r: r["branch"])
        return Table(
            "rentals_by_branch",
            [C("branch", "Branch"), C("agreements", "Active agreements", "int"), C("rent", "Annual rent (AED)", "money")],
            rows,
            [S("Annual rent (AED)", money(sum((r["rent"] for r in rows), ZERO)))],
        )  # fmt: skip

    def rental_renewals(self, rf: RF) -> Table:
        by_id = {a["id"]: a for a in self._agreements(rf)}
        rows = []
        for a in by_id.values():
            prev = by_id.get(a["renewed_from_id"]) if a["renewed_from_id"] else None
            if prev is None or not (rf.d_from <= a["start_date"] <= rf.d_to):
                continue
            rows.append({"branch": a["branch_name"], "landlord": a["landlord"], "previous_end": prev["end_date"],
                         "start": a["start_date"], "end": a["end_date"], "previous_rent": money(prev["annual_rent"]),
                         "rent": money(a["annual_rent"])})  # fmt: skip
        rows.sort(key=lambda r: r["start"], reverse=True)
        return Table(
            "rental_renewals",
            [C("branch", "Branch"), C("landlord", "Landlord"), C("previous_end", "Previous end date", "date"),
             C("start", "New start date", "date"), C("end", "New end date", "date"),
             C("previous_rent", "Previous annual rent (AED)", "money"), C("rent", "New annual rent (AED)", "money")],
            rows,
            [S("Renewals", len(rows), "int")],
            ["Listed by the start date of the renewal agreement."],
        )  # fmt: skip

    def _cheques(self, rf: RF) -> list[Row]:
        k = ("chq", rf.branch_id)
        if k not in self._memo:
            self._memo[k], _ = self.rent.cheques(
                self.today,
                None,
                rf.branch_id,
                None,
                None,
                None,
                None,
                None,
                None,
                "date",
                False,
                1,
                ALL_ROWS,
            )
        return self._memo[k]  # type: ignore[no-any-return]

    def _pdc_buckets(self, rf: RF) -> list[tuple[str, Callable[[Row], bool]]]:
        t, f, e = self.today, rf.d_from, rf.d_to
        return [
            ("Pending (all)", lambda c: c["status"] == "Pending"),
            ("Pending - overdue", lambda c: c["status"] == "Pending" and c["cheque_date"] < t),
            ("Pending - upcoming", lambda c: c["status"] == "Pending" and c["cheque_date"] >= t),
            ("Cleared in period", lambda c: c["status"] == "Cleared" and c["cleared_on"] is not None and f <= c["cleared_on"] <= e),
            ("Bounced in period", lambda c: c["status"] == "Bounced" and c["bounced_on"] is not None and f <= c["bounced_on"] <= e),
        ]  # fmt: skip

    def pdc_summary(self, rf: RF) -> Table:
        chq = self._cheques(rf)
        rows = []
        for label, pred in self._pdc_buckets(rf):
            sel = [c for c in chq if pred(c)]
            enbd = money(sum((c["amount"] for c in sel if c["bank"] == "ENBD"), ZERO))
            adcb = money(sum((c["amount"] for c in sel if c["bank"] == "ADCB"), ZERO))
            rows.append(
                {
                    "status": label,
                    "count": len(sel),
                    "enbd": enbd,
                    "adcb": adcb,
                    "total": money(enbd + adcb),
                }
            )
        total = {r["status"]: r["total"] for r in rows}
        return Table(
            "pdc_summary",
            [C("status", "Status"), C("count", "Cheques", "int"), C("enbd", "ENBD (AED)", "money"),
             C("adcb", "ADCB (AED)", "money"), C("total", "Total (AED)", "money")],
            rows,
            [S("Total pending (AED)", total["Pending (all)"]), S("Cleared in period (AED)", total["Cleared in period"]),
             S("Bounced in period (AED)", total["Bounced in period"]),
             S("Overdue pending (AED)", total["Pending - overdue"])],
            ["Pending, overdue and upcoming are today's position. Cleared and bounced count cheques whose cleared / "
             "bounced date is inside the period. Pending and bounced cheques are never counted as cleared payments."],
        )  # fmt: skip

    def pdc_by_branch(self, rf: RF) -> Table:
        chq = self._cheques(rf)
        buckets = dict(self._pdc_buckets(rf))
        rows = []
        for b in sorted({c["branch_name"] for c in chq}):
            mine = [c for c in chq if c["branch_name"] == b]
            amt = partial(_amount, mine, buckets)
            rows.append({"branch": b, "pending": amt("Pending (all)"), "overdue": amt("Pending - overdue"),
                         "cleared": amt("Cleared in period"), "bounced": amt("Bounced in period")})  # fmt: skip
        return Table(
            "pdc_by_branch",
            [C("branch", "Branch"), C("pending", "Pending (AED)", "money"), C("overdue", "Overdue pending (AED)", "money"),
             C("cleared", "Cleared in period (AED)", "money"), C("bounced", "Bounced in period (AED)", "money")],
            rows,
            [S(lbl, money(sum((r[k] for r in rows), ZERO))) for lbl, k in
             (("Pending (AED)", "pending"), ("Overdue pending (AED)", "overdue"),
              ("Cleared in period (AED)", "cleared"), ("Bounced in period (AED)", "bounced"))],
        )  # fmt: skip

    def _cheque_rows(self, chq: list[Row]) -> list[Row]:
        return [{"cheque_no": c["cheque_no"], "bank": c["bank"], "branch": c["branch_name"], "landlord": c["landlord"],
                 "cheque_date": c["cheque_date"], "amount": money(c["amount"]), "status": c["status"],
                 "cleared_on": c["cleared_on"], "bounced_on": c["bounced_on"]} for c in chq]  # fmt: skip

    _CHQ_COLS = [("cheque_no", "Cheque number", "text"), ("bank", "Bank", "text"), ("branch", "Branch", "text"),
                 ("landlord", "Landlord", "text"), ("cheque_date", "Cheque date", "date"),
                 ("amount", "Amount (AED)", "money"), ("status", "Status", "text"),
                 ("cleared_on", "Cleared on", "date"), ("bounced_on", "Bounced on", "date")]  # fmt: skip

    def pdc_cheques(self, rf: RF) -> Table:
        sel = [c for c in self._cheques(rf) if rf.d_from <= c["cheque_date"] <= rf.d_to]
        rows = self._cheque_rows(sel)
        return Table(
            "pdc_cheques", [C(*c) for c in self._CHQ_COLS], rows,  # type: ignore[arg-type]
            [S("Cheques", len(rows), "int"), S("Total amount (AED)", money(sum((r["amount"] for r in rows), ZERO)))],
        )  # fmt: skip

    def pdc_clearance(self, rf: RF) -> Table:
        sel = [
            c
            for c in self._cheques(rf)
            if c["status"] == "Cleared"
            and c["cleared_on"]
            and rf.d_from <= c["cleared_on"] <= rf.d_to
        ]
        rows = self._cheque_rows(sel)
        enbd = money(sum((r["amount"] for r in rows if r["bank"] == "ENBD"), ZERO))
        adcb = money(sum((r["amount"] for r in rows if r["bank"] == "ADCB"), ZERO))
        return Table(
            "pdc_clearance", [C(*c) for c in self._CHQ_COLS], rows,  # type: ignore[arg-type]
            [S("Cleared cheques", len(rows), "int"), S("ENBD cleared (AED)", enbd), S("ADCB cleared (AED)", adcb),
             S("Total cleared (AED)", money(enbd + adcb))],
            ["A cleared cheque is deducted from its bank exactly once, on the cheque date (Step 10)."],
        )  # fmt: skip

    # ---- tasks and missing reports -----------------------------------------------------------------------
    def tasks_by_branch(self, rf: RF) -> Table:
        rows = [{"branch": r["branch_name"], "total": int(r["total"]), "to_do": int(r["to_do"]),
                 "in_progress": int(r["in_progress"]), "done": int(r["done"]), "overdue": int(r["overdue"])}
                for r in self.repo.tasks_by_branch(rf.branch_id, self.today)]  # fmt: skip
        s = lambda k: sum(r[k] for r in rows)  # noqa: E731
        return Table(
            "tasks_by_branch",
            [C("branch", "Branch"), C("total", "Total", "int"), C("to_do", "To Do", "int"),
             C("in_progress", "In Progress", "int"), C("done", "Completed", "int"), C("overdue", "Overdue", "int")],
            rows,
            [S("Total tasks", s("total"), "int"), S("To Do", s("to_do"), "int"), S("In Progress", s("in_progress"), "int"),
             S("Completed", s("done"), "int"), S("Overdue", s("overdue"), "int")],
            ["Overdue = due date passed (Dubai) and not Done. Tasks are shown as at today; the date range does not apply."],
        )  # fmt: skip

    def tasks_completed(self, rf: RF) -> Table:
        rows = self.repo.tasks_completed(rf.branch_id, rf.d_from, rf.d_to)
        for r in rows:
            r["days_late"] = (r["completed_on"] - r["due_date"]).days if r["due_date"] else None
        return Table(
            "tasks_completed",
            [C("title", "Task"), C("branch_name", "Branch"), C("assignee_name", "Assigned to"),
             C("due_date", "Due date", "date"), C("completed_on", "Completed on", "date"),
             C("days_late", "Days after due date", "int"), C("completed_by_name", "Completed by")],
            rows,
            [S("Tasks completed", len(rows), "int")],
            ["Days after due date is negative when the task was finished early."],
        )  # fmt: skip

    def _missing(self, rf: RF) -> Any:
        return self.dash.missing(rf.branch_id, rf.d_from, rf.d_to, self.today)

    def missing_by_branch(self, rf: RF) -> Table:
        m = self._missing(rf)
        notes = [
            "Counts days from the reporting start up to today (Dubai), exactly as the dashboard does."
        ]
        if m.status != "ok":
            return Table(
                "missing_by_branch",
                [C("branch", "Branch")],
                [],
                notes=notes + ["No days are due in this period."],
            )
        days = (m.date_to - m.date_from).days + 1 if m.date_from and m.date_to else 0
        miss = {b.branch_id: b.missing_count for b in m.branches}
        rows = []
        for b in self.names(rf):
            if rf.branch_id is not None and b["branch_id"] != rf.branch_id:
                continue
            missing = miss.get(b["branch_id"], 0)
            rows.append({"branch": b["branch_name"], "expected": days, "submitted": days - missing,
                         "missing": missing, "compliance": _pct(days - missing, days)})  # fmt: skip
        return Table(
            "missing_by_branch",
            [C("branch", "Branch"), C("expected", "Reports expected", "int"), C("submitted", "Reports submitted", "int"),
             C("missing", "Missing reports", "int"), C("compliance", "Reporting compliance (%)", "pct")],
            rows,
            [S("Reports expected", m.expected, "int"), S("Reports received", m.received, "int"),
             S("Missing reports", m.missing_count, "int"), S("Reporting compliance (%)", _pct(m.received, m.expected), "pct")],
            notes,
        )  # fmt: skip

    def missing_by_date(self, rf: RF) -> Table:
        m = self._missing(rf)
        by_day: dict[date, list[str]] = defaultdict(list)
        for b in m.branches:
            for d in b.dates:
                by_day[d].append(b.branch_name)
        rows = [
            {"date": d, "missing": len(n), "branches": ", ".join(sorted(n))}
            for d, n in sorted(by_day.items(), reverse=True)
        ]
        return Table(
            "missing_by_date",
            [C("date", "Date", "date"), C("missing", "Branches missing a report", "int"), C("branches", "Branches")],
            rows,
            [S("Missing reports", m.missing_count, "int"), S("Days with a gap", len(rows), "int")],
        )  # fmt: skip

    # ---- activity history --------------------------------------------------------------------------------
    def activity(self, rf: RF) -> Table:
        tables = MODULE_KEYS[rf.module] if rf.module else None
        limit = None if rf.export else rf.page_size
        rows_db, total = self.repo.activity(
            rf.d_from,
            rf.d_to,
            tables,
            rf.action,
            rf.actor_id,
            rf.source,
            rf.q,
            limit,
            (rf.page - 1) * rf.page_size,
        )
        if rf.export and total > MAX_EXPORT_ROWS:
            raise UnprocessableError("Too many activity rows to export; narrow the dates or module")
        rows = []
        for r in rows_db:
            mod = ACTIVITY_MODULES.get(r["table_name"], (r["table_name"], ""))[0]
            rows.append({
                "occurred_at": r["occurred_at"].astimezone(BUSINESS_TZ).replace(tzinfo=None),
                "user": actor_label(r["actor_user_id"], r["actor_name"], r["table_name"], r["action"])[0],
                "source": actor_label(r["actor_user_id"], r["actor_name"], r["table_name"], r["action"])[1],
                "action": ACTION_LABELS.get(r["action"], str(r["action"]).replace("_", " ").capitalize()),
                "module": mod, "record": record_label(r["table_name"], r["old_values"], r["new_values"]) or str(r["record_id"] or "")[:8],
                "summary": change_summary(r["action"], r["old_values"], r["new_values"]), "reason": r["reason"] or "",
            })  # fmt: skip
        return Table(
            "activity",
            [C("occurred_at", "Date and time (Dubai)", "datetime"), C("user", "User"), C("source", "Source"), C("action", "Action"),
             C("module", "Module"), C("record", "Related record"), C("summary", "Change summary"), C("reason", "Reason")],
            rows,
            [S("Matching entries", total, "int")],
            ["Read-only view of the append-only audit log. Passwords, tokens, keys and bookkeeping columns are never shown."],
            total=total, paged=True,
        )  # fmt: skip

    # ---- dispatch ----------------------------------------------------------------------------------------
    def build(self, key: str, rf: RF) -> Table:
        if key not in CATALOG:
            raise NotFoundError("Unknown report")
        rf = self.validate(rf)
        return getattr(self, key)(rf)  # type: ignore[no-any-return]

    def run(self, key: str, rf: RF, sort: str | None, desc: bool) -> ReportOut:
        table = self.build(key, rf)
        rows = table.rows
        total = table.total if table.total is not None else len(rows)
        if not table.paged:
            if sort:
                if sort not in {c.key for c in table.columns}:
                    raise UnprocessableError(
                        "Unknown sort column", fields={"sort": ["Choose a listed column"]}
                    )
                rows = sorted(
                    rows,
                    key=lambda r: (
                        r.get(sort) is None,
                        r.get(sort) if r.get(sort) is not None else 0,
                    ),
                    reverse=desc,
                )
                if desc:  # keep empty values last
                    rows = [r for r in rows if r.get(sort) is not None] + [
                        r for r in rows if r.get(sort) is None
                    ]
            start = (rf.page - 1) * rf.page_size
            rows = rows[start : start + rf.page_size]
        return self._out(key, rf, table, rows, total)

    def full(self, key: str, rf: RF) -> ReportOut:
        """Complete filtered dataset, independent of pagination (used by the exports)."""
        table = self.build(key, RF(**{**rf.__dict__, "export": True}))
        total = table.total if table.total is not None else len(table.rows)
        if total > MAX_EXPORT_ROWS:
            raise UnprocessableError("Too many rows to export; narrow the dates, branch or filters")
        return self._out(key, rf, table, table.rows, total, page_size=max(total, 1))

    def _out(
        self,
        key: str,
        rf: RF,
        table: Table,
        rows: list[Row],
        total: int,
        page_size: int | None = None,
    ) -> ReportOut:
        return ReportOut(
            key=key, title=CATALOG[key][1], description=CATALOG[key][2], filters=self.applied(rf),
            columns=table.columns, rows=rows, total=total, page=rf.page if page_size is None else 1,
            page_size=page_size or rf.page_size, summary=table.summary, notes=table.notes,
            generated_at=datetime.now(BUSINESS_TZ),
        )  # fmt: skip

    # ---- charts ------------------------------------------------------------------------------------------
    def charts(self, rf: RF) -> ChartSet:
        rf = self.validate(rf)

        def pts(rows: list[Row], lab: str, **cols: str) -> list[ChartPoint]:
            return [
                ChartPoint(label=str(r[lab]), values={k: r[v] for k, v in cols.items()})
                for r in rows
            ]

        sales = self.sales_trend(rf).rows
        coll = self.collections_trend(rf)
        by_branch = self.sales_by_branch(rf).rows
        shop = self.shop_expenses_by_date(rf).rows
        cats = self.ho_by_category(rf).rows
        ho_day = self.repo.ho_by_day(rf.branch_id, rf.d_from, rf.d_to)
        sup = sorted(
            self.supplier_balances(RF(rf.d_from, rf.d_to)).rows,
            key=lambda r: r["outstanding"],
            reverse=True,
        )
        emp = self.employees(rf).summary
        pdc = self.pdc_summary(rf).rows
        tsk = self.tasks_by_branch(rf).summary
        ca = self.cash_accounts(rf).rows
        coll_tot = {s.label: s.value for s in coll.summary}
        shop_tot = money(sum((r["excl"] for r in shop), ZERO))
        ho_tot = self.ho_totals(rf)
        ho_excl = calc.head_office_excl_savings(*ho_tot)

        # savings trend by period: shop savings + head office savings, bucketed like the other period charts
        sav_acc: dict[str, Row] = {}
        for lbl, s in self.grouped(rf):
            sav_acc[lbl] = {"shop": money(s["shop_savings"]), "ho": ZERO}
        for d, h in ho_day.items():
            lbl = _bucket(d, rf.period)
            sav_acc.setdefault(lbl, {"shop": ZERO, "ho": ZERO})["ho"] += money(h["savings"])
        sav_rows = [
            {
                "label": k,
                "shop": v["shop"],
                "ho": money(v["ho"]),
                "total": money(v["shop"] + v["ho"]),
            }
            for k, v in sorted(sav_acc.items())
        ]

        def chart(
            key: str,
            title: str,
            kind: str,
            unit: str,
            series: list[str],
            points: list[ChartPoint],
            empty: str,
        ) -> Chart:
            nonzero = any(float(v or 0) != 0 for p in points for v in p.values.values())
            return Chart(key=key, title=title, kind=kind, unit=unit, series=series,  # type: ignore[arg-type]
                         points=points if nonzero else [], empty_message=empty)  # fmt: skip

        none = "No records in the selected period."
        charts = [
            chart("sales_trend", "Sales trend", "line", "AED", ["Sales"], pts(sales, "period", Sales="sales"), none),
            chart("branch_sales", "Sales by branch", "bar", "AED", ["Sales"], pts(by_branch, "branch", Sales="sales"), none),
            chart("collections_method", "Collections by payment method", "pie", "AED", ["Amount"],
                  [ChartPoint(label=lbl, values={"Amount": coll_tot.get(k, ZERO)}) for lbl, k in
                   (("Cash", "Cash received (AED)"), ("POS", "POS received (AED)"),
                    ("Bank transfer", "Bank transfers (AED)"), ("Payment link", "Payment links (AED)"))], none),
            chart("expenses_split", "Shop vs head office expenses", "bar", "AED", ["Amount"],
                  [ChartPoint(label="Shop expenses", values={"Amount": shop_tot}),
                   ChartPoint(label="Head office expenses", values={"Amount": ho_excl})], none),
            chart("expense_categories", "Head office expenses by category", "pie", "AED", ["Amount"],
                  pts(cats, "label", Amount="excl"), "No head office expenses in the selected period."),
            chart("savings_trend", "Savings trend", "line", "AED", ["Shop savings", "Head office savings", "Total"],
                  pts(sav_rows, "label", **{"Shop savings": "shop", "Head office savings": "ho", "Total": "total"}), "No savings recorded in the selected period."),
            chart("cash_bank", "Cash and bank balances", "bar", "AED", ["Closing balance"],
                  pts(ca, "account", **{"Closing balance": "closing"}), "Opening balances are not configured yet."),
            chart("supplier_outstanding", "Supplier outstanding (top 10)", "bar", "AED", ["Outstanding"],
                  pts([r for r in sup if r["outstanding"] > 0][:10], "supplier", Outstanding="outstanding"), "No supplier owes money."),
            chart("employee_status", "Employee status", "pie", "count", ["Employees"],
                  [ChartPoint(label=s.label, values={"Employees": s.value}) for s in emp[:3]], "No employees recorded."),
            chart("cheque_status", "Rental cheque status", "bar", "AED", ["Amount"],
                  [ChartPoint(label=r["status"], values={"Amount": r["total"]}) for r in pdc if r["status"] in
                   ("Pending (all)", "Cleared in period", "Bounced in period")], "No cheques recorded."),
            chart("task_status", "Task status", "pie", "count", ["Tasks"],
                  [ChartPoint(label=s.label, values={"Tasks": s.value}) for s in tsk[1:4]], "No tasks recorded."),
        ]  # fmt: skip
        return ChartSet(
            filters=self.applied(rf), charts=charts, generated_at=datetime.now(BUSINESS_TZ)
        )
