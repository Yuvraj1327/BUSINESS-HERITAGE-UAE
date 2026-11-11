"""Order dashboard, pickup & delivery operations and order reports (Step 13).
Reports reuse the Step 12 `Table` / `ReportOut` / export engine; they add order data but do not touch the Step 12 reports,
daily-report sales or reconciliation. Revenue = final payable of non-cancelled orders (by order date); collections = payments
recorded on those orders; outstanding = revenue - collections."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from app.api.authz import BranchScope
from app.core import orders as rules
from app.core.calculations import ZERO, money
from app.core.exceptions import NotFoundError, UnprocessableError
from app.repositories.order_repository import OrderFilter, OrderRepository
from app.schemas.analytics import AppliedFilters, ReportCatalogItem, ReportOut
from app.schemas.orders import OrderDashboard, OrderKpis, OrderPage, Section
from app.services.analytics_service import MAX_EXPORT_ROWS, MAX_RANGE_DAYS, C, S, Table
from app.services.base import BaseService
from app.services.order_service import order_row
from app.utils.time import BUSINESS_TZ, dubai_today

Row = dict[str, Any]

SECTIONS = [  # key, title, view, sort, desc
    ("pickups_today", "Today's Pickup Schedule", "pickups_today", "pickup", False),
    ("deliveries_today", "Today's Delivery Schedule", "deliveries_today", "delivery", False),
    ("pending_pickups", "Pending Pickups", "pending_pickups", "pickup", False),
    ("processing", "Orders Currently Processing", "processing", "delivery", False),
    ("ready", "Ready for Delivery", "ready", "delivery", False),
    ("overdue_deliveries", "Overdue Deliveries", "overdue_deliveries", "delivery", False),
    ("incomplete", "Unassigned or Incomplete Orders", "incomplete", "created", True),
    ("recent", "Recent Orders", "recent", "created", True),
]
OPERATION_VIEWS = {
    k: (k, s, d)
    for k, s, d in (
        ("pickups_today", "pickup", False),
        ("deliveries_today", "delivery", False),
        ("pending_pickups", "pickup", False),
        ("overdue_pickups", "pickup", False),
        ("processing", "delivery", False),
        ("ready", "delivery", False),
        ("out_for_delivery", "delivery", False),
        ("overdue_deliveries", "delivery", False),
        ("incomplete", "created", True),
    )
}

OperationView = Literal[
    "pickups_today", "deliveries_today", "pending_pickups", "overdue_pickups", "processing", "ready",
    "out_for_delivery", "overdue_deliveries", "incomplete",
]  # fmt: skip

CATALOG = {
    "order_summary": ("Order totals", "Order count, completed, cancelled, revenue, collections, outstanding and average order value."),
    "orders_by_category": ("Orders by service category", "Orders, revenue and collections for each service category."),
    "orders_by_type": ("Standard vs Express", "Orders, revenue and collections for Standard and Express orders."),
    "orders_trend": ("Order trend", "Orders, revenue and collections for each day or week."),
    "orders_by_branch": ("Orders by branch", "Orders, revenue and collections for each branch."),
    "order_payments_by_method": ("Order payments by method", "Payments recorded on orders in the period, by payment method."),
    "outstanding_orders": ("Outstanding order payments", "Orders (not cancelled) that still have a balance to collect."),
    "orders_list": ("Order list", "Every order matching the filters (the export of the Orders screen)."),
}  # fmt: skip


class OrderInsightsService(BaseService):
    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.repo = OrderRepository(session)

    # ---- operations ------------------------------------------------------------------------------------
    @staticmethod
    def _now0() -> datetime:
        return rules.day_bounds(dubai_today())[0]

    def operations(
        self, scope: BranchScope, view: str, day: date | None, f: OrderFilter, sort: str | None,
        desc: bool | None, page: int, page_size: int,
    ) -> OrderPage:  # fmt: skip
        if view not in OPERATION_VIEWS:
            raise NotFoundError("Unknown operations view")
        _, default_sort, default_desc = OPERATION_VIEWS[view]
        d = day or dubai_today()
        f = OrderFilter(
            **{
                **f.__dict__,
                "branch_id": scope.resolve(f.branch_id),
                "view": view,
                "day_bounds": rules.day_bounds(d),
                "now0": self._now0(),
            }  # fmt: skip
        )
        rows, total = self.repo.list_orders(
            f,
            sort or default_sort,
            default_desc if desc is None else desc,
            page_size,
            (page - 1) * page_size,
        )
        now0 = self._now0()
        return OrderPage(
            items=[order_row(r, now0) for r in rows], total=total, page=page, page_size=page_size
        )

    def operation_counts(
        self, scope: BranchScope, day: date | None, f: OrderFilter
    ) -> dict[str, int]:
        d = day or dubai_today()
        base = {
            **f.__dict__,
            "branch_id": scope.resolve(f.branch_id),
            "day_bounds": rules.day_bounds(d),
            "now0": self._now0(),
        }
        return {k: self.repo.count(OrderFilter(**{**base, "view": k})) for k in OPERATION_VIEWS}

    # ---- dashboard -------------------------------------------------------------------------------------
    def dashboard(self, scope: BranchScope, day: date | None, f: OrderFilter) -> OrderDashboard:
        d = day or dubai_today()
        branch = scope.resolve(f.branch_id)
        bounds, now0 = rules.day_bounds(d), self._now0()
        base = OrderFilter(
            **{**f.__dict__, "branch_id": branch, "day_bounds": bounds, "now0": now0}
        )
        total_all = self.repo.count(base)
        total = (
            total_all
            if f.status
            else total_all
            - self.repo.count(OrderFilter(**{**base.__dict__, "status": "Cancelled"}))
        )
        month_start = d.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        month = OrderFilter(**{**base.__dict__, "order_from": month_start, "order_to": month_end})
        revenue = ZERO
        for r in self.repo.grouped(month, "1", "k"):
            revenue += Decimal(str(r["revenue"]))
        sections = []
        for key, title, view, sort, desc in SECTIONS:
            sf = OrderFilter(**{**base.__dict__, "view": view})
            rows, count = self.repo.list_orders(sf, sort, desc, 8)
            sections.append(
                Section(key=key, title=title, count=count, items=[order_row(r, now0) for r in rows])
            )
        by_key = {s.key: s.count for s in sections}
        return OrderDashboard(
            date=d,
            kpis=OrderKpis(
                total_orders=total,
                todays_pickups=by_key["pickups_today"],
                todays_deliveries=by_key["deliveries_today"],
                monthly_revenue=money(revenue),
                outstanding_payments=money(self.repo.outstanding_total(base)),
            ),
            sections=sections,
        )

    # ---- reports ---------------------------------------------------------------------------------------
    def catalog(self) -> list[ReportCatalogItem]:
        return [
            ReportCatalogItem(key=k, category="Orders", title=v[0], description=v[1])
            for k, v in CATALOG.items()
        ]

    def _validate(self, d_from: date, d_to: date) -> None:
        if d_from > d_to:
            raise UnprocessableError(
                "Start date is after end date",
                fields={"date_from": ["Must not be after the end date"]},
            )
        if d_to > dubai_today():
            raise UnprocessableError(
                "End date is in the future", fields={"date_to": ["Cannot be in the future"]}
            )
        if (d_to - d_from).days + 1 > MAX_RANGE_DAYS:
            raise UnprocessableError(
                f"Choose at most {MAX_RANGE_DAYS} days",
                fields={"date_from": [f"Range is limited to {MAX_RANGE_DAYS} days"]},
            )

    def _build(
        self,
        key: str,
        f: OrderFilter,
        period: str,
        d_from: date,
        d_to: date,
        branch: uuid.UUID | None,
    ) -> Table:
        def metric_rows(rows: list[Row], label: str) -> list[Row]:
            out = []
            for r in rows:
                billable = r["orders"] - r["cancelled"]
                out.append({
                    label: r[label], "orders": r["orders"], "completed": r["completed"], "cancelled": r["cancelled"],
                    "standard": r["standard"], "express": r["express"], "revenue": money(r["revenue"]),
                    "collected": money(r["collected"]), "outstanding": money(r["outstanding"]),
                    "aov": money(Decimal(str(r["revenue"])) / billable) if billable else None,
                })  # fmt: skip
            return out

        def cols(label_key: str, label: str) -> list:
            return [C(label_key, label), C("orders", "Orders", "int"), C("completed", "Completed", "int"),
                    C("cancelled", "Cancelled", "int"), C("standard", "Standard", "int"), C("express", "Express", "int"),
                    C("revenue", "Revenue (AED)", "money"), C("collected", "Collected (AED)", "money"),
                    C("outstanding", "Outstanding (AED)", "money"), C("aov", "Average order (AED)", "money")]  # fmt: skip

        notes = [
            "Revenue is the final payable amount of non-cancelled orders, by order date. It is separate from daily report sales.",
            "Collected is the sum of payments recorded on those orders; Outstanding = Revenue - Collected.",
        ]
        if key in ("orders_by_category", "orders_by_type", "orders_by_branch", "orders_trend"):
            expr, label, lab_name = {
                "orders_by_category": ("sc.name", "category", "Service category"),
                "orders_by_type": ("o.service_type", "service_type", "Service type"),
                "orders_by_branch": ("b.name", "branch", "Branch"),
                "orders_trend": (
                    "o.order_date::text"
                    if period == "day"
                    else "'Week of ' || date_trunc('week', o.order_date)::date::text",
                    "period",
                    "Day" if period == "day" else "Week",
                ),
            }[key]
            rows = metric_rows(self.repo.grouped(f, expr, label), label)
            return Table(key, cols(label, lab_name), rows, self._totals(f), notes)
        if key == "order_summary":
            t = self._totals(f)
            raw = self.repo.grouped(f, "1", "k")
            rows = metric_rows([{**r, "k": "All orders"} for r in raw], "k") if raw else []
            columns = cols("k", "Scope")
            return Table(key, columns, rows, t, notes)
        if key == "order_payments_by_method":
            data = self.repo.payment_summary(branch, d_from, d_to)
            by = {r["method"]: r for r in data}
            rows = [
                {"method": m, "payments": int(by[m]["n"]) if m in by else 0, "total": money(by[m]["total"]) if m in by else ZERO}
                for m in rules.PAYMENT_METHODS
            ]  # fmt: skip
            total = money(sum((r["total"] for r in rows), ZERO))
            return Table(
                key, [C("method", "Payment method"), C("payments", "Payments", "int"), C("total", "Amount (AED)", "money")],
                rows, [S("Total payments (AED)", total), S("Payments", sum(r["payments"] for r in rows), "int")],
                ["Payments are listed by the date they were recorded. They are not part of Cash & Banks or daily reports."],
            )  # fmt: skip
        if key in ("outstanding_orders", "orders_list"):
            of = OrderFilter(**f.__dict__)
            rows_db, n_rows = self.repo.list_orders(of, "delivery", False, MAX_EXPORT_ROWS + 1)
            if n_rows > MAX_EXPORT_ROWS:
                raise UnprocessableError(
                    "Too many rows to export; narrow the dates, branch or filters"
                )
            now0 = self._now0()
            if key == "outstanding_orders":
                rows_db = [
                    r for r in rows_db if r["status"] != "Cancelled" and r["outstanding"] > 0
                ]
            rows = [self._list_row(r, now0) for r in rows_db]
            columns = [
                C("order_no", "Order"), C("order_date", "Order date", "date"), C("customer", "Customer"), C("mobile", "Mobile"),
                C("branch", "Branch"), C("area", "Area"), C("category", "Service category"), C("service_type", "Type"),
                C("status", "Status"), C("payment_status", "Payment"), C("pickup_at", "Pickup", "datetime"),
                C("delivery_at", "Delivery", "datetime"), C("final_payable", "Final payable (AED)", "money"),
                C("collected", "Collected (AED)", "money"), C("outstanding", "Outstanding (AED)", "money"),
            ]  # fmt: skip
            live = [r for r in rows if r["status"] != "Cancelled"]
            summary = [
                S("Orders", len(rows), "int"),
                S("Revenue (AED)", money(sum((r["final_payable"] for r in live), ZERO))),
                S("Collected (AED)", money(sum((r["collected"] for r in live), ZERO))),
                S("Outstanding (AED)", money(sum((r["outstanding"] for r in live), ZERO))),
            ]  # fmt: skip
            return Table(key, columns, rows, summary, notes[:1])
        raise NotFoundError("Unknown report")

    @staticmethod
    def _list_row(r: Row, now0: datetime) -> Row:
        del now0
        return {
            "order_no": r["order_no"], "order_date": r["order_date"], "customer": r["customer_name"], "mobile": r["mobile"],
            "branch": r["branch_name"], "area": r["area"], "category": r["category"], "service_type": r["service_type"],
            "status": r["status"], "payment_status": r["payment_status"], "pickup_at": r["pickup_at"],
            "delivery_at": r["delivery_at"], "final_payable": money(r["final_payable"]),
            "collected": money(r["amount_collected"]), "outstanding": money(r["outstanding"]),
        }  # fmt: skip

    def _totals(self, f: OrderFilter) -> list:
        rows = self.repo.grouped(f, "1", "k")
        r = (
            rows[0]
            if rows
            else {
                k: 0
                for k in (
                    "orders",
                    "completed",
                    "cancelled",
                    "standard",
                    "express",
                    "revenue",
                    "collected",
                    "outstanding",
                    "held_cancelled",
                )
            }
        )
        billable = int(r["orders"]) - int(r["cancelled"])
        revenue = Decimal(str(r["revenue"]))
        return [
            S("Order count", int(r["orders"]), "int"), S("Completed orders", int(r["completed"]), "int"),
            S("Cancelled orders", int(r["cancelled"]), "int"), S("Standard orders", int(r["standard"]), "int"),
            S("Express orders", int(r["express"]), "int"), S("Revenue (AED)", money(revenue)),
            S("Collections (AED)", money(r["collected"])), S("Outstanding payments (AED)", money(r["outstanding"])),
            S("Average order value (AED)", money(revenue / billable) if billable else None),
            S("Held on cancelled orders (AED)", money(r["held_cancelled"])),
        ]  # fmt: skip

    def report(
        self, scope: BranchScope, key: str, d_from: date, d_to: date, period: str, f: OrderFilter,
        sort: str | None, desc: bool, page: int, page_size: int, export: bool = False,
    ) -> ReportOut:  # fmt: skip
        if key not in CATALOG:
            raise NotFoundError("Unknown report")
        self._validate(d_from, d_to)
        branch = scope.resolve(f.branch_id)
        f = OrderFilter(
            **{**f.__dict__, "branch_id": branch, "order_from": d_from, "order_to": d_to}
        )
        table = self._build(key, f, period, d_from, d_to, branch)
        rows = table.rows
        if sort:
            if sort not in {c.key for c in table.columns}:
                raise UnprocessableError(
                    "Unknown sort column", fields={"sort": ["Choose a listed column"]}
                )
            rows = sorted(
                rows,
                key=lambda r: (r.get(sort) is None, r.get(sort) if r.get(sort) is not None else 0),
                reverse=desc,
            )
        total = len(rows)
        if not export:
            rows = rows[(page - 1) * page_size : page * page_size]
        branch_name = "All Branches"
        if branch and (b := self.repo.branch(branch)):
            branch_name = b["name"]
        return ReportOut(
            key=key, title=CATALOG[key][0], description=CATALOG[key][1],
            filters=AppliedFilters(date_from=d_from, date_to=d_to, period=period, branch_id=branch, branch_name=branch_name),  # type: ignore[arg-type]
            columns=table.columns, rows=rows, total=total, page=1 if export else page,
            page_size=max(total, 1) if export else page_size, summary=table.summary, notes=table.notes,
            generated_at=datetime.now(BUSINESS_TZ),
        )  # fmt: skip
