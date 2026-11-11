import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository

Row = dict[str, Any]

_REPORT_COLS = """r.id, r.report_date, r.branch_id, b.name as branch_name, r.total_sales, r.order_count,
       r.cash_received, r.pos_amount, r.bank_transfer, r.link_payment, r.shop_expenses, r.shop_savings,
       r.created_at"""
_REPORT_FROM = "from public.daily_reports r join public.branches b on b.id = r.branch_id"
_ACTIVE = "r.voided_at is null"
_BRANCH_FILTER = "(cast(:b as uuid) is null or r.branch_id = cast(:b as uuid))"
_SUMS = """count(*) as report_count,
       coalesce(sum(r.total_sales), 0) as total_sales, coalesce(sum(r.order_count), 0) as total_orders,
       coalesce(sum(r.cash_received), 0) as cash_received, coalesce(sum(r.pos_amount), 0) as pos_amount,
       coalesce(sum(r.bank_transfer), 0) as bank_transfer, coalesce(sum(r.link_payment), 0) as link_payment,
       coalesce(sum(r.shop_expenses), 0) as shop_expenses, coalesce(sum(r.shop_savings), 0) as shop_savings"""


class ReportRepository(BaseRepository):
    """Queries only. Rules live in the services; the caller's BranchScope narrows `branch` and RLS enforces it again."""

    # ---- single reports --------------------------------------------------------------------------------
    def insert(self, branch_id: uuid.UUID, report_date: date, v: dict[str, Any]) -> uuid.UUID:
        row = self.session.execute(
            text(
                """insert into public.daily_reports
                     (report_date, branch_id, total_sales, order_count, cash_received, pos_amount,
                      bank_transfer, link_payment, shop_expenses, shop_savings)
                   values (:d, :b, :ts, :oc, :cash, :pos, :bt, :lp, :se, :ss) returning id"""
            ),
            {
                "d": report_date,
                "b": branch_id,
                "ts": v["total_sales"],
                "oc": v["order_count"],
                "cash": v["cash_received"],
                "pos": v["pos_amount"],
                "bt": v["bank_transfer"],
                "lp": v["link_payment"],
                "se": v["shop_expenses"],
                "ss": v["shop_savings"],
            },
        ).one()
        return row[0]  # type: ignore[no-any-return]

    def get(self, report_id: uuid.UUID) -> Row | None:
        r = (
            self.session.execute(
                text(f"select {_REPORT_COLS} {_REPORT_FROM} where r.id = :i and {_ACTIVE}"),
                {"i": report_id},
            )
            .mappings()
            .first()
        )
        return None if r is None else dict(r)

    def list_page(
        self,
        branch: uuid.UUID | None,
        d_from: date | None,
        d_to: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int]:
        where = (
            f"where {_ACTIVE} and {_BRANCH_FILTER}"
            " and (cast(:f as date) is null or r.report_date >= cast(:f as date))"
            " and (cast(:t as date) is null or r.report_date <= cast(:t as date))"
        )
        params = {"b": branch, "f": d_from, "t": d_to}
        total = self.session.execute(
            text(f"select count(*) {_REPORT_FROM} {where}"), params
        ).scalar_one()
        rows = (
            self.session.execute(
                text(
                    f"select {_REPORT_COLS} {_REPORT_FROM} {where}"
                    " order by r.report_date desc, b.sort_order, r.created_at desc limit :lim offset :off"
                ),
                {**params, "lim": limit, "off": offset},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows], int(total)

    def list_range(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        rows = (
            self.session.execute(
                text(
                    f"select {_REPORT_COLS} {_REPORT_FROM}"
                    f" where {_ACTIVE} and {_BRANCH_FILTER} and r.report_date between :f and :t"
                    " order by r.report_date desc, b.sort_order"
                ),
                {"b": branch, "f": d_from, "t": d_to},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def void(self, report_id: uuid.UUID, reason: str) -> None:
        self.session.execute(
            text("select public.void_daily_report(:i, :r)"), {"i": report_id, "r": reason}
        )

    # ---- aggregates ------------------------------------------------------------------------------------
    def totals(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> Row:
        r = (
            self.session.execute(
                text(
                    f"select {_SUMS} from public.daily_reports r"
                    f" where {_ACTIVE} and {_BRANCH_FILTER} and r.report_date between :f and :t"
                ),
                {"b": branch, "f": d_from, "t": d_to},
            )
            .mappings()
            .one()
        )
        return dict(r)

    def totals_by_branch(self, d_from: date, d_to: date) -> dict[uuid.UUID, Row]:
        rows = (
            self.session.execute(
                text(
                    f"select r.branch_id, {_SUMS} from public.daily_reports r"
                    f" where {_ACTIVE} and r.report_date between :f and :t group by r.branch_id"
                ),
                {"f": d_from, "t": d_to},
            )
            .mappings()
            .all()
        )
        return {r["branch_id"]: dict(r) for r in rows}

    def totals_by_day(self, d_from: date, d_to: date) -> dict[date, Row]:
        rows = (
            self.session.execute(
                text(
                    f"select r.report_date, {_SUMS} from public.daily_reports r"
                    f" where {_ACTIVE} and r.report_date between :f and :t group by r.report_date"
                ),
                {"f": d_from, "t": d_to},
            )
            .mappings()
            .all()
        )
        return {r["report_date"]: dict(r) for r in rows}

    # ---- branches and reporting start ------------------------------------------------------------------
    def branches_for_summary(self, d_from: date, d_to: date) -> list[Row]:
        """Active branches, plus any inactive branch that still has reports in the period (so sums add up)."""
        rows = (
            self.session.execute(
                text(
                    """select b.id as branch_id, b.name as branch_name from public.branches b
                       where b.is_active or exists (select 1 from public.daily_reports r
                          where r.branch_id = b.id and r.voided_at is null and r.report_date between :f and :t)
                       order by b.sort_order, b.name"""
                ),
                {"f": d_from, "t": d_to},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def reporting_start(self) -> date | None:
        return self.session.execute(text("select public.reporting_start_date()")).scalar_one()  # type: ignore[no-any-return]

    def active_branch_count(self, branch: uuid.UUID | None) -> int:
        return int(
            self.session.execute(
                text(
                    "select count(*) from public.branches b where b.is_active"
                    " and (cast(:b as uuid) is null or b.id = cast(:b as uuid))"
                ),
                {"b": branch},
            ).scalar_one()
        )

    def missing_cells(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        """(branch, day) pairs without an active report, in branch order then date order."""
        rows = (
            self.session.execute(
                text(
                    """select b.id as branch_id, b.name as branch_name, d.day::date as day
                         from public.branches b
                         cross join generate_series(cast(:f as date), cast(:t as date), interval '1 day') as d(day)
                        where b.is_active and (cast(:b as uuid) is null or b.id = cast(:b as uuid))
                          and not exists (select 1 from public.daily_reports r
                                           where r.branch_id = b.id and r.report_date = d.day::date
                                             and r.voided_at is null)
                        order by b.sort_order, b.name, d.day"""
                ),
                {"b": branch, "f": d_from, "t": d_to},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def get_branch(self, branch_id: uuid.UUID) -> Row | None:
        r = (
            self.session.execute(
                text("select id, name, is_active from public.branches where id = :b"),
                {"b": branch_id},
            )
            .mappings()
            .first()
        )
        return None if r is None else dict(r)


class HeadOfficeRepository(BaseRepository):
    """Head-office expenses (owner-only table: an owner session sees rows, anyone else sees none)."""

    def by_branch(self, d_from: date, d_to: date) -> dict[uuid.UUID | None, Row]:
        rows = (
            self.session.execute(
                text(
                    """select h.branch_id, count(*) as cnt, coalesce(sum(h.amount), 0) as total,
                              coalesce(sum(h.amount) filter (where h.is_saving), 0) as savings
                         from public.head_office_expenses h
                        where h.voided_at is null and h.expense_date between :f and :t
                        group by h.branch_id"""
                ),
                {"f": d_from, "t": d_to},
            )
            .mappings()
            .all()
        )
        return {r["branch_id"]: dict(r) for r in rows}

    def by_day(self, d_from: date, d_to: date) -> dict[date, Row]:
        rows = (
            self.session.execute(
                text(
                    """select h.expense_date as day, coalesce(sum(h.amount), 0) as total,
                              coalesce(sum(h.amount) filter (where h.is_saving), 0) as savings
                         from public.head_office_expenses h
                        where h.voided_at is null and h.expense_date between :f and :t
                        group by h.expense_date"""
                ),
                {"f": d_from, "t": d_to},
            )
            .mappings()
            .all()
        )
        return {r["day"]: dict(r) for r in rows}

    def rows(
        self, branch: uuid.UUID | None, d_from: date, d_to: date, limit: int = 500
    ) -> list[Row]:
        r = (
            self.session.execute(
                text(
                    """select h.id, h.expense_date, h.branch_id, b.name as branch_name, c.name as category,
                              h.amount, h.paid_from, h.is_saving, h.note
                         from public.head_office_expenses h
                         join public.expense_categories c on c.id = h.category_id
                         left join public.branches b on b.id = h.branch_id
                        where h.voided_at is null and h.expense_date between :f and :t
                          and (cast(:b as uuid) is null or h.branch_id = cast(:b as uuid))
                        order by h.expense_date desc, h.created_at desc limit :lim"""
                ),
                {"b": branch, "f": d_from, "t": d_to, "lim": limit},
            )
            .mappings()
            .all()
        )
        return [dict(x) for x in r]


class BalanceRepository(BaseRepository):
    """Reads the approved balance function (owner only inside the database)."""

    def balances(self, as_of: date) -> Row:
        r = (
            self.session.execute(
                text("select * from public.app_balances(cast(:d as date))"), {"d": as_of}
            )
            .mappings()
            .one()
        )
        return dict(r)


class AlertRepository(BaseRepository):
    """Counts for the 'Needs attention' list, from the existing tables (owner-only through RLS)."""

    def counts(self, today: date) -> dict[str, Decimal | int]:
        r = (
            self.session.execute(
                text(
                    """select
  (select count(*) from public.employees e where e.archived_at is null and e.visa_expiry is not null and not e.visa_cancelled
      and not (e.status = 'Leave' and e.leave_start + interval '6 months' < cast(:t as date))
      and e.visa_expiry <= cast(:t as date) + 30) as visas_30,
  (select count(*) from public.employees e where e.archived_at is null and (e.visa_cancelled
      or (e.status = 'Leave' and e.leave_start + interval '6 months' < cast(:t as date)))) as visas_cancelled,
  (select count(*) from public.employees e where e.archived_at is null and e.status = 'Leave' and not e.visa_cancelled
      and e.leave_start + interval '6 months' >= cast(:t as date)
      and e.leave_start + interval '6 months' <= cast(:t as date) + 30) as leave_limit_30,
  (select count(*) from public.employees e where e.archived_at is null and e.passport_expiry is not null
      and e.passport_expiry <= cast(:t as date) + 30) as passports_30,
  (select count(*) from public.tasks k where k.due_date is not null and k.due_date < cast(:t as date)
      and k.status <> 'Done') as tasks_overdue,
  (select count(*) from public.tasks k where k.due_date = cast(:t as date) and k.status <> 'Done') as tasks_due_today,
  (select count(*) from public.tasks k where k.due_date > cast(:t as date) and k.due_date <= cast(:t as date) + 7
      and k.status <> 'Done') as tasks_due_7,
  (select count(*) from public.trade_licenses l where l.archived_at is null and l.expiry_date <= cast(:t as date) + 30) as licenses_30,
  (select count(*) from public.trade_licenses l where l.archived_at is null
      and l.expiry_date between cast(:t as date) + 31 and cast(:t as date) + 90) as licenses_renewal_90,
  (select count(*) from public.rental_agreements a where a.status = 'Active'
      and a.end_date >= cast(:t as date) and a.end_date <= cast(:t as date) + 30) as rentals_ending_30,
  (select count(*) from public.rental_agreements a where a.status = 'Active'
      and a.end_date between cast(:t as date) + 31 and cast(:t as date) + 90) as rentals_renewal_90,
  (select count(*) from public.rental_agreements a where a.status = 'Active'
      and a.end_date < cast(:t as date)) as rentals_expired,
  (select count(*) from public.pdc_cheques c where c.status = 'Bounced'
      and not exists (select 1 from public.pdc_cheques r where r.replaces_id = c.id)) as cheques_bounced,
  (select count(*) from public.pdc_cheques c where c.status = 'Pending'
      and c.cheque_date < cast(:t as date)) as pdc_overdue,
  (select count(*) from public.pdc_cheques c where c.status = 'Pending'
      and c.cheque_date between cast(:t as date) and cast(:t as date) + 7) as pdc_due_7,
  (select count(*) from public.pdc_cheques c where c.status = 'Pending'
      and c.cheque_date between cast(:t as date) + 8 and cast(:t as date) + 30) as pdc_due_30,
  (select count(*) from public.suppliers s join public.v_supplier_outstanding v on v.supplier_id = s.id
      where s.is_active and v.outstanding > 0) as suppliers_owed,
  (select coalesce(sum(v.outstanding), 0) from public.suppliers s join public.v_supplier_outstanding v on v.supplier_id = s.id
      where s.is_active) as suppliers_owed_total"""
                ),
                {"t": today},
            )
            .mappings()
            .one()
        )
        return dict(r)
