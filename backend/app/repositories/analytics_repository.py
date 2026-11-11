"""Read-only aggregate queries that the Reports module needs and no earlier repository already offers.
Everything else is reused from the Step 7-11 repositories (daily report sums, ledger, balances, suppliers, HR, rentals)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository
from app.repositories.report_repository import _ACTIVE, _BRANCH_FILTER, _SUMS

Row = dict[str, Any]


class AnalyticsRepository(BaseRepository):
    def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        return [dict(r) for r in self.session.execute(text(sql), params or {}).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any] | None = None) -> Row | None:
        r = self.session.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None

    # ---- daily reports (the Step 7 sums, optionally for one branch) -------------------------------------
    def daily_by_day(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> dict[date, Row]:
        rows = self._all(
            f"select r.report_date, {_SUMS} from public.daily_reports r"  # noqa: S608
            f" where {_ACTIVE} and {_BRANCH_FILTER} and r.report_date between :f and :t group by r.report_date",
            {"b": branch, "f": d_from, "t": d_to},
        )
        return {r["report_date"]: r for r in rows}

    # ---- head office expenses ---------------------------------------------------------------------------
    _HO_WHERE = """h.voided_at is null and h.expense_date between :f and :t
                   and (cast(:b as uuid) is null or h.branch_id = cast(:b as uuid))"""

    def ho_by_day(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> dict[date, Row]:
        rows = self._all(
            f"""select h.expense_date as day, count(*) as cnt, coalesce(sum(h.amount), 0) as total,
                       coalesce(sum(h.amount) filter (where h.is_saving), 0) as savings
                  from public.head_office_expenses h where {self._HO_WHERE} group by h.expense_date""",  # noqa: S608
            {"b": branch, "f": d_from, "t": d_to},
        )
        return {r["day"]: r for r in rows}

    def ho_grouped(
        self, group: str, branch: uuid.UUID | None, d_from: date, d_to: date
    ) -> list[Row]:
        """group = 'category' | 'source' | 'branch'."""
        col = {
            "category": "c.name",
            "source": "h.paid_from",
            "branch": "coalesce(b.name, 'All Branches')",
        }[group]
        return self._all(
            f"""select {col} as label, count(*) as cnt, coalesce(sum(h.amount), 0) as total,
                       coalesce(sum(h.amount) filter (where h.is_saving), 0) as savings
                  from public.head_office_expenses h
                  join public.expense_categories c on c.id = h.category_id
                  left join public.branches b on b.id = h.branch_id
                 where {self._HO_WHERE} group by 1 order by total desc, 1""",  # noqa: S608
            {"b": branch, "f": d_from, "t": d_to},
        )

    def ho_list(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        return self._all(
            f"""select h.expense_date, c.name as category, coalesce(b.name, 'All Branches') as branch_name,
                       h.paid_from, h.amount, h.is_saving, h.note, p.full_name as created_by_name
                  from public.head_office_expenses h
                  join public.expense_categories c on c.id = h.category_id
                  left join public.branches b on b.id = h.branch_id
                  left join public.profiles p on p.user_id = h.created_by
                 where {self._HO_WHERE} order by h.expense_date desc, h.created_at desc""",  # noqa: S608
            {"b": branch, "f": d_from, "t": d_to},
        )

    # ---- suppliers ---------------------------------------------------------------------------------------
    def supplier_period(self, supplier: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        """Position (opening dues, all-time outstanding from the approved view) plus activity inside the period."""
        return self._all(
            """select s.id, s.name, s.category, s.is_active, v.opening_outstanding, v.new_dues as dues_all,
                      v.payments as paid_all, v.outstanding,
                      coalesce(p.dues, 0) as dues_period, coalesce(p.paid, 0) as paid_period,
                      coalesce(p.pay_count, 0) as pay_count
                 from public.suppliers s
                 join public.v_supplier_outstanding v on v.supplier_id = s.id
                 left join lateral (
                   select sum(e.amount) filter (where e.kind = 'due') as dues,
                          sum(e.amount) filter (where e.kind = 'payment') as paid,
                          count(*) filter (where e.kind = 'payment') as pay_count
                     from public.supplier_entries e
                    where e.supplier_id = s.id and e.voided_at is null and e.entry_date between :f and :t) p on true
                where (cast(:s as uuid) is null or s.id = cast(:s as uuid))
                order by lower(s.name)""",
            {"s": supplier, "f": d_from, "t": d_to},
        )

    def supplier_entries(self, supplier: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        return self._all(
            """select e.entry_date, s.name as supplier_name, e.kind, e.amount, e.paid_from,
                      coalesce(b.name, '') as branch_name, e.reference, e.note
                 from public.supplier_entries e join public.suppliers s on s.id = e.supplier_id
                 left join public.branches b on b.id = e.branch_id
                where e.voided_at is null and e.entry_date between :f and :t
                  and (cast(:s as uuid) is null or e.supplier_id = cast(:s as uuid))
                order by e.entry_date desc, e.created_at desc""",
            {"s": supplier, "f": d_from, "t": d_to},
        )

    # ---- tasks -------------------------------------------------------------------------------------------
    def tasks_by_branch(self, branch: uuid.UUID | None, today: date) -> list[Row]:
        return self._all(
            """select coalesce(b.name, 'All Branches') as branch_name, count(*) as total,
                      count(*) filter (where k.status = 'To Do') as to_do,
                      count(*) filter (where k.status = 'In Progress') as in_progress,
                      count(*) filter (where k.status = 'Done') as done,
                      count(*) filter (where k.status <> 'Done' and k.due_date < cast(:t as date)) as overdue
                 from public.tasks k left join public.branches b on b.id = k.branch_id
                where (cast(:b as uuid) is null or k.branch_id = cast(:b as uuid))
                group by 1 order by 1""",
            {"b": branch, "t": today},
        )

    def tasks_completed(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        return self._all(
            """select k.title, coalesce(b.name, 'All Branches') as branch_name,
                      coalesce(a.full_name, 'Unassigned') as assignee_name, k.due_date,
                      (k.completed_at at time zone 'Asia/Dubai')::date as completed_on,
                      cu.full_name as completed_by_name
                 from public.tasks k left join public.branches b on b.id = k.branch_id
                 left join public.profiles a on a.user_id = k.assignee_user_id
                 left join public.profiles cu on cu.user_id = k.completed_by
                where k.status = 'Done' and (k.completed_at at time zone 'Asia/Dubai')::date between :f and :t
                  and (cast(:b as uuid) is null or k.branch_id = cast(:b as uuid))
                order by k.completed_at desc""",
            {"b": branch, "f": d_from, "t": d_to},
        )

    # ---- trade licence renewals --------------------------------------------------------------------------
    def license_renewals(self, branch: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        return self._all(
            """select r.renewed_on, b.name as branch_name, l.license_no, r.previous_expiry, r.new_expiry,
                      r.renewal_fee, r.note
                 from public.license_renewals r join public.trade_licenses l on l.id = r.license_id
                 join public.branches b on b.id = l.branch_id
                where r.renewed_on between :f and :t and (cast(:b as uuid) is null or l.branch_id = cast(:b as uuid))
                order by r.renewed_on desc, l.license_no""",
            {"b": branch, "f": d_from, "t": d_to},
        )

    # ---- activity history (the existing append-only audit_log) -------------------------------------------
    def activity(
        self,
        d_from: date,
        d_to: date,
        tables: list[str] | None,
        action: str | None,
        actor: uuid.UUID | None,
        source: str | None,
        q: str | None,
        limit: int | None,
        offset: int,
    ) -> tuple[list[Row], int]:
        where = """(a.occurred_at at time zone 'Asia/Dubai')::date between :f and :t
                   and (cast(:acts as text) is null or a.action = cast(:acts as text))
                   and (cast(:actor as uuid) is null or a.actor_user_id = cast(:actor as uuid))
                   and (cast(:source as text) is null
                        or (cast(:source as text) = 'user' and a.actor_user_id is not null)
                        or (cast(:source as text) = 'system' and a.actor_user_id is null))
                   and (:no_tables or a.table_name = any(:tables))
                   and (cast(:q as text) is null or a.record_id ilike '%' || cast(:q as text) || '%'
                        or coalesce(a.reason, '') ilike '%' || cast(:q as text) || '%')"""
        p = {
            "f": d_from, "t": d_to, "acts": action, "actor": actor, "source": source, "q": q,
            "no_tables": not tables, "tables": tables or [],
        }  # fmt: skip
        n = self._one(f"select count(*) as n from public.audit_log a where {where}", p)  # noqa: S608
        rows = self._all(
            f"""select a.id, a.occurred_at, a.actor_user_id, p.full_name as actor_name, a.action, a.table_name,
                       a.record_id, a.reason, a.old_values, a.new_values
                  from public.audit_log a left join public.profiles p on p.user_id = a.actor_user_id
                 where {where} order by a.id desc"""  # noqa: S608
            + (" limit :lim offset :off" if limit is not None else ""),
            {**p, "lim": limit, "off": offset},
        )
        return rows, int(n["n"]) if n else 0

    def actors(self) -> list[Row]:
        return self._all("select user_id, full_name from public.profiles order by lower(full_name)")
