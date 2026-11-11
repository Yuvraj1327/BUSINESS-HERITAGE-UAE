"""Step 9 data access: employees, visas & passports, trade licenses, compliance alerts.
Queries only (rules live in the services). Runs as `authenticated` under RLS (owner-only tables)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository

Row = dict[str, Any]

# Six CALENDAR months (PostgreSQL clamps month ends like the Python helper). Used by every query so the
# list, the summary and the alerts can never disagree.
LIMIT = "(e.leave_start + interval '6 months')::date"
CANCELLED_BY_LEAVE = f"(e.status = 'Leave' and {LIMIT} < cast(:t as date))"
EFF_CANCELLED = f"(e.visa_cancelled or {CANCELLED_BY_LEAVE})"
EFF_STATUS = f"(case when {EFF_CANCELLED} then 'Visa Cancelled' when e.status = 'Leave' then 'On Leave' else 'Active' end)"

EMPLOYEE_SELECT = f"""
select e.*, b.name as branch_name, pc.full_name as created_by_name, pu.full_name as updated_by_name,
       {EFF_CANCELLED} as eff_cancelled, {EFF_STATUS} as eff_status
  from public.employees e
  join public.branches b on b.id = e.branch_id
  left join public.profiles pc on pc.user_id = e.created_by
  left join public.profiles pu on pu.user_id = e.updated_by
"""

EMPLOYEE_SORT = {
    "name": "lower(e.full_name)",
    "branch": "b.name",
    "salary": "e.monthly_salary",
    "status": EFF_STATUS,
    "leave_start": "e.leave_start",
    "created": "e.created_at",
}


def _bucket_sql(col: str, red: int, amber: int) -> str:
    return (
        f"(case when {col} is null then 'not_recorded' when {col} < cast(:t as date) then 'expired' "
        f"when {col} <= cast(:t as date) + {red} then 'urgent' "
        f"when {col} <= cast(:t as date) + {amber} then 'upcoming' else 'normal' end)"
    )


VISA_BUCKET = (
    f"(case when {EFF_CANCELLED} then 'cancelled' else {_bucket_sql('e.visa_expiry', 30, 90)} end)"
)
PASSPORT_BUCKET = _bucket_sql("e.passport_expiry", 30, 180)
LICENSE_BUCKET = _bucket_sql("l.expiry_date", 30, 90)


class HrRepository(BaseRepository):
    def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        return [dict(r) for r in self.session.execute(text(sql), params or {}).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any] | None = None) -> Row | None:
        r = self.session.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None

    def set_reason(self, reason: str | None) -> None:
        self.session.execute(
            text("select set_config('app.audit_reason', :r, true)"), {"r": reason or ""}
        )

    def lock(self, key: int) -> None:
        self.session.execute(text("select pg_advisory_xact_lock(:k)"), {"k": key})

    def branch_exists(self, branch_id: uuid.UUID) -> dict[str, Any] | None:
        return self._one(
            "select id, name, is_active from public.branches where id = :i", {"i": branch_id}
        )

    def record_history(self, table: str, record_id: uuid.UUID, limit: int = 100) -> list[Row]:
        return self._all(
            """select a.id, a.occurred_at, p.full_name as actor_name, a.action, a.table_name, a.record_id, a.reason,
                      a.old_values, a.new_values
                 from public.audit_log a left join public.profiles p on p.user_id = a.actor_user_id
                where a.table_name = :t and a.record_id = :r order by a.id desc limit :n""",
            {"t": table, "r": str(record_id), "n": limit},
        )

    # ---------------------------------------------------------------- employees
    def employee(self, id_: uuid.UUID, today: date, for_update: bool = False) -> Row | None:
        sql = EMPLOYEE_SELECT + " where e.id = :i" + (" for update of e" if for_update else "")
        return self._one(sql, {"i": id_, "t": today})

    def employees(
        self,
        today: date,
        q: str | None,
        branch_id: uuid.UUID | None,
        status: str | None,
        include_archived: bool,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Row], int]:
        where: list[str] = ["1 = 1"]
        p: dict[str, Any] = {"t": today}
        if not include_archived:
            where.append("e.archived_at is null")
        if q:
            where.append("e.full_name ilike :q")
            p["q"] = f"%{q}%"
        if branch_id:
            where.append("e.branch_id = :b")
            p["b"] = branch_id
        if status:
            where.append(f"{EFF_STATUS} = :s")
            p["s"] = status
        w = " and ".join(where)
        total = self._one(
            f"select count(*) as n from public.employees e join public.branches b on b.id = e.branch_id where {w}",
            p,
        )
        order = (
            EMPLOYEE_SORT[sort]
            + (" desc" if desc else " asc")
            + " nulls last, lower(e.full_name), e.id"
        )
        rows = self._all(
            f"{EMPLOYEE_SELECT} where {w} order by {order} limit :lim offset :off",
            {**p, "lim": page_size, "off": (page - 1) * page_size},
        )
        return rows, int(total["n"]) if total else 0

    def employee_summary(self, today: date) -> Row:
        r = self._one(
            f"""select
  count(*) filter (where e.status = 'Active' and not {EFF_CANCELLED}) as total_active,
  count(*) filter (where e.status = 'Leave' and not {EFF_CANCELLED}) as on_leave,
  count(*) filter (where e.status = 'Leave' and not e.visa_cancelled and {LIMIT} >= cast(:t as date)
                     and {LIMIT} <= cast(:t as date) + 30) as close_to_limit,
  count(*) filter (where {EFF_CANCELLED}) as visa_cancelled,
  coalesce(sum(e.monthly_salary) filter (where e.status = 'Active' and not {EFF_CANCELLED}), 0) as monthly_payroll,
  count(*) filter (where e.status = 'Active' and not {EFF_CANCELLED}) as payroll_employees
from public.employees e where e.archived_at is null""",
            {"t": today},
        )
        assert r is not None
        return r

    def leave_watch(self, today: date) -> list[Row]:
        """On leave and within 30 days of (or past) the limit, most urgent first. Cancelled-by-flag staff are excluded."""
        return self._all(
            f"""{EMPLOYEE_SELECT}
                where e.archived_at is null and e.status = 'Leave' and not e.visa_cancelled
                  and {LIMIT} <= cast(:t as date) + 30
                order by {LIMIT} asc, lower(e.full_name)""",
            {"t": today},
        )

    def leave_counts(self, today: date) -> Row:
        r = self._one(
            f"""select
  count(*) filter (where e.status = 'Leave' and not {EFF_CANCELLED}) as on_leave,
  count(*) filter (where e.status = 'Leave' and not e.visa_cancelled and {LIMIT} > cast(:t as date)
                     and {LIMIT} <= cast(:t as date) + 30) as approaching,
  count(*) filter (where e.status = 'Leave' and not e.visa_cancelled and {LIMIT} = cast(:t as date)) as limit_reached,
  count(*) filter (where {CANCELLED_BY_LEAVE} and not e.visa_cancelled) as visa_cancelled_by_leave
from public.employees e where e.archived_at is null""",
            {"t": today},
        )
        assert r is not None
        return r

    def insert_employee(self, v: Row) -> uuid.UUID:
        return self.session.execute(
            text(
                """insert into public.employees (full_name, branch_id, role_title, monthly_salary, passport_expiry,
                                                 visa_expiry, notes)
                   values (:full_name, :branch_id, :role_title, :monthly_salary, :passport_expiry, :visa_expiry, :notes)
                   returning id"""
            ),
            v,
        ).scalar_one()

    def update_employee(self, id_: uuid.UUID, v: Row) -> None:
        self.session.execute(
            text(
                """update public.employees set full_name = :full_name, branch_id = :branch_id, role_title = :role_title,
                          monthly_salary = :monthly_salary, passport_expiry = :passport_expiry,
                          visa_expiry = :visa_expiry, notes = :notes where id = :id"""
            ),
            {**v, "id": id_},
        )

    def set_employee_state(
        self,
        id_: uuid.UUID,
        status: str,
        leave_start: date | None,
        visa_cancelled: bool,
        visa_cancelled_date: date | None,
    ) -> None:
        self.session.execute(
            text(
                """update public.employees set status = :s, leave_start = :ls, visa_cancelled = :vc,
                          visa_cancelled_date = :vcd where id = :id"""
            ),
            {
                "s": status,
                "ls": leave_start,
                "vc": visa_cancelled,
                "vcd": visa_cancelled_date,
                "id": id_,
            },
        )

    def set_expiry(self, id_: uuid.UUID, column: str, value: date) -> None:
        assert column in {"visa_expiry", "passport_expiry"}
        self.session.execute(
            text(f"update public.employees set {column} = :v where id = :id"),  # noqa: S608 - allow-listed
            {"v": value, "id": id_},
        )

    def archive_employee(self, id_: uuid.UUID, reason: str) -> None:
        self.session.execute(
            text(
                "update public.employees set archived_at = now(), archived_by = auth.uid(), archive_reason = :r where id = :id"
            ),
            {"r": reason, "id": id_},
        )

    # ---------------------------------------------------------------- visas & passports
    def compliance(
        self,
        kind: str,
        today: date,
        q: str | None,
        branch_id: uuid.UUID | None,
        bucket: str | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Row], int]:
        col, bucket_sql = (
            ("e.visa_expiry", VISA_BUCKET)
            if kind == "visa"
            else ("e.passport_expiry", PASSPORT_BUCKET)
        )
        where: list[str] = ["e.archived_at is null"]
        p: dict[str, Any] = {"t": today}
        if q:
            where.append("e.full_name ilike :q")
            p["q"] = f"%{q}%"
        if branch_id:
            where.append("e.branch_id = :b")
            p["b"] = branch_id
        if bucket:
            where.append(f"{bucket_sql} = :k")
            p["k"] = bucket
        w = " and ".join(where)
        total = self._one(f"select count(*) as n from public.employees e where {w}", p)
        cancelled_first = (
            f"({EFF_CANCELLED}) desc, " if kind == "visa" and sort == "expiry" and not desc else ""
        )
        order = {
            "expiry": f"{cancelled_first}{col} {'desc' if desc else 'asc'} nulls last",
            "name": f"lower(e.full_name) {'desc' if desc else 'asc'}",
            "branch": f"b.name {'desc' if desc else 'asc'}",
        }[sort]
        rows = self._all(
            f"""select e.id as employee_id, e.full_name as employee_name, e.branch_id, b.name as branch_name,
                       {EFF_STATUS} as employment_status, {col} as expiry_date, {EFF_CANCELLED} as eff_cancelled
                  from public.employees e join public.branches b on b.id = e.branch_id
                 where {w} order by {order}, lower(e.full_name), e.id limit :lim offset :off""",
            {**p, "lim": page_size, "off": (page - 1) * page_size},
        )
        return rows, int(total["n"]) if total else 0

    def compliance_counts(self, kind: str, today: date) -> Row:
        bucket_sql = VISA_BUCKET if kind == "visa" else PASSPORT_BUCKET
        r = self._one(
            f"""select
  count(*) filter (where {bucket_sql} = 'expired') as expired,
  count(*) filter (where {bucket_sql} = 'urgent') as urgent,
  count(*) filter (where {bucket_sql} = 'upcoming') as upcoming,
  count(*) filter (where {bucket_sql} = 'normal') as normal,
  count(*) filter (where {bucket_sql} = 'not_recorded') as not_recorded,
  count(*) filter (where {bucket_sql} = 'cancelled') as cancelled
from public.employees e where e.archived_at is null""",
            {"t": today},
        )
        assert r is not None
        return r

    def expiry_history(self, id_: uuid.UUID, column: str) -> list[Row]:
        assert column in {"visa_expiry", "passport_expiry"}
        return self._all(
            f"""select a.occurred_at, p.full_name as actor_name, a.reason,
                       a.old_values ->> '{column}' as old_expiry, a.new_values ->> '{column}' as new_expiry
                  from public.audit_log a left join public.profiles p on p.user_id = a.actor_user_id
                 where a.table_name = 'employees' and a.record_id = :r
                   and (a.action = 'INSERT' or (a.old_values ->> '{column}') is distinct from (a.new_values ->> '{column}'))
                 order by a.id desc limit 100""",  # noqa: S608 - allow-listed column
            {"r": str(id_)},
        )

    # ---------------------------------------------------------------- trade licenses
    LICENSE_SELECT = """
select l.*, b.name as branch_name, pu.full_name as updated_by_name,
       (select count(*) from public.license_renewals r where r.license_id = l.id) as renewal_count,
       (select max(r.renewed_on) from public.license_renewals r where r.license_id = l.id) as last_renewed_on
  from public.trade_licenses l
  join public.branches b on b.id = l.branch_id
  left join public.profiles pu on pu.user_id = l.updated_by
"""
    LICENSE_SORT = {
        "expiry": "l.expiry_date",
        "branch": "b.name",
        "number": "lower(l.license_no)",
        "fee": "l.renewal_fee",
    }

    def license(self, id_: uuid.UUID, for_update: bool = False) -> Row | None:
        sql = self.LICENSE_SELECT + " where l.id = :i" + (" for update of l" if for_update else "")
        return self._one(sql, {"i": id_})

    def licenses(
        self,
        today: date,
        q: str | None,
        branch_id: uuid.UUID | None,
        status: str | None,
        include_archived: bool,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Row], int]:
        where: list[str] = ["1 = 1"]
        p: dict[str, Any] = {"t": today}
        if not include_archived:
            where.append("l.archived_at is null")
        if q:
            where.append(
                "(b.name ilike :q or l.license_no ilike :q or coalesce(l.authority, '') ilike :q)"
            )
            p["q"] = f"%{q}%"
        if branch_id:
            where.append("l.branch_id = :b")
            p["b"] = branch_id
        if status:
            where.append(f"{LICENSE_BUCKET} = :k")
            p["k"] = status
        w = " and ".join(where)
        total = self._one(
            f"select count(*) as n from public.trade_licenses l join public.branches b on b.id = l.branch_id where {w}",
            p,
        )
        order = (
            self.LICENSE_SORT[sort] + (" desc" if desc else " asc") + ", lower(l.license_no), l.id"
        )
        rows = self._all(
            f"{self.LICENSE_SELECT} where {w} order by {order} limit :lim offset :off",
            {**p, "lim": page_size, "off": (page - 1) * page_size},
        )
        return rows, int(total["n"]) if total else 0

    def license_summary(self, today: date) -> Row:
        r = self._one(
            """select count(*) as total,
  count(*) filter (where l.expiry_date < cast(:t as date)) as expired,
  count(*) filter (where l.expiry_date >= cast(:t as date) and l.expiry_date <= cast(:t as date) + 30) as expiring_30,
  count(*) filter (where l.expiry_date >= cast(:t as date) and l.expiry_date <= cast(:t as date) + 60) as expiring_60,
  coalesce(sum(l.renewal_fee) filter (where l.expiry_date <= cast(:t as date) + 90), 0) as renewal_fees_due,
  count(*) filter (where l.expiry_date <= cast(:t as date) + 90) as fees_due_count
from public.trade_licenses l where l.archived_at is null""",
            {"t": today},
        )
        assert r is not None
        return r

    def insert_license(self, v: Row) -> uuid.UUID:
        return self.session.execute(
            text(
                """insert into public.trade_licenses (branch_id, license_no, authority, expiry_date, renewal_fee, notes)
                   values (:branch_id, :license_no, :authority, :expiry_date, :renewal_fee, :notes) returning id"""
            ),
            v,
        ).scalar_one()

    def update_license(self, id_: uuid.UUID, v: Row) -> None:
        self.session.execute(
            text(
                """update public.trade_licenses set branch_id = :branch_id, license_no = :license_no,
                          authority = :authority, expiry_date = :expiry_date, renewal_fee = :renewal_fee,
                          notes = :notes where id = :id"""
            ),
            {**v, "id": id_},
        )

    def set_license_expiry(self, id_: uuid.UUID, expiry: date) -> None:
        self.session.execute(
            text("update public.trade_licenses set expiry_date = :e where id = :id"),
            {"e": expiry, "id": id_},
        )

    def archive_license(self, id_: uuid.UUID, reason: str) -> None:
        self.session.execute(
            text(
                "update public.trade_licenses set archived_at = now(), archived_by = auth.uid(), archive_reason = :r where id = :id"
            ),
            {"r": reason, "id": id_},
        )

    def insert_renewal(self, v: Row) -> uuid.UUID:
        return self.session.execute(
            text(
                """insert into public.license_renewals (license_id, renewed_on, previous_expiry, new_expiry, renewal_fee,
                                                        note, client_key)
                   values (:license_id, :renewed_on, :previous_expiry, :new_expiry, :renewal_fee, :note, :client_key)
                   returning id"""
            ),
            v,
        ).scalar_one()

    def renewals(self, license_id: uuid.UUID) -> list[Row]:
        return self._all(
            """select r.*, p.full_name as created_by_name from public.license_renewals r
                 left join public.profiles p on p.user_id = r.created_by
                where r.license_id = :i order by r.created_at desc, r.id""",
            {"i": license_id},
        )

    def renewal(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            """select r.*, p.full_name as created_by_name from public.license_renewals r
                 left join public.profiles p on p.user_id = r.created_by where r.id = :i""",
            {"i": id_},
        )

    # ---------------------------------------------------------------- alerts (one row per record + condition)
    def alert_rows(self, today: date) -> list[Row]:
        base = "e.archived_at is null"
        return self._all(
            f"""
select 'visa_expired' as kind, e.id as record_id, e.full_name as name, b.name as branch_name, e.visa_expiry as due
  from public.employees e join public.branches b on b.id = e.branch_id
 where {base} and not {EFF_CANCELLED} and e.visa_expiry < cast(:t as date)
union all
select 'visa_expiring', e.id, e.full_name, b.name, e.visa_expiry
  from public.employees e join public.branches b on b.id = e.branch_id
 where {base} and not {EFF_CANCELLED} and e.visa_expiry between cast(:t as date) and cast(:t as date) + 30
union all
select 'passport_expired', e.id, e.full_name, b.name, e.passport_expiry
  from public.employees e join public.branches b on b.id = e.branch_id
 where {base} and e.passport_expiry < cast(:t as date)
union all
select 'passport_expiring', e.id, e.full_name, b.name, e.passport_expiry
  from public.employees e join public.branches b on b.id = e.branch_id
 where {base} and e.passport_expiry between cast(:t as date) and cast(:t as date) + 30
union all
select 'leave_limit_approaching', e.id, e.full_name, b.name, {LIMIT}
  from public.employees e join public.branches b on b.id = e.branch_id
 where {base} and e.status = 'Leave' and not e.visa_cancelled
   and {LIMIT} between cast(:t as date) and cast(:t as date) + 30
union all
select 'visa_cancelled_by_leave', e.id, e.full_name, b.name, {LIMIT}
  from public.employees e join public.branches b on b.id = e.branch_id
 where {base} and e.status = 'Leave' and not e.visa_cancelled and {LIMIT} < cast(:t as date)
union all
select 'license_expired', l.id, l.license_no, b.name, l.expiry_date
  from public.trade_licenses l join public.branches b on b.id = l.branch_id
 where l.archived_at is null and l.expiry_date < cast(:t as date)
union all
select 'license_expiring', l.id, l.license_no, b.name, l.expiry_date
  from public.trade_licenses l join public.branches b on b.id = l.branch_id
 where l.archived_at is null and l.expiry_date between cast(:t as date) and cast(:t as date) + 30
union all
select 'license_renewal_due', l.id, l.license_no, b.name, l.expiry_date
  from public.trade_licenses l join public.branches b on b.id = l.branch_id
 where l.archived_at is null and l.expiry_date between cast(:t as date) + 31 and cast(:t as date) + 90
order by 5 asc, 1, 3""",
            {"t": today},
        )
