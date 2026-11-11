"""Step 10 data access: rental agreements, PDC cheques, rental alerts. Queries only (rules live in the services).
Runs as `authenticated` under RLS (owner-only tables)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository

Row = dict[str, Any]

# Displayed agreement status from the real dates; mirrors core.rentals.agreement_status (a test compares them).
AGREEMENT_STATUS = """(case when a.status = 'Renewed' then 'Renewed' when a.status = 'Terminated' then 'Terminated'
  when a.end_date < cast(:t as date) then 'Expired' when a.start_date > cast(:t as date) then 'Scheduled'
  when a.end_date <= cast(:t as date) + 30 then 'Expiring' else 'Active' end)"""

AGREEMENT_SELECT = f"""
select a.*, b.name as branch_name, {AGREEMENT_STATUS} as display_status,
       (select n.id from public.rental_agreements n where n.renewed_from_id = a.id) as renewed_to_id,
       s.live_cheques, s.schedule_total, s.pending_count, s.cleared_count, s.bounced_count, s.next_cheque_date,
       pc.full_name as created_by_name, pu.full_name as updated_by_name
  from public.rental_agreements a
  join public.branches b on b.id = a.branch_id
  left join public.profiles pc on pc.user_id = a.created_by
  left join public.profiles pu on pu.user_id = a.updated_by
  cross join lateral (
    select count(*) filter (where not x.sup) as live_cheques,
           coalesce(sum(x.amount) filter (where not x.sup), 0) as schedule_total,
           count(*) filter (where x.status = 'Pending') as pending_count,
           count(*) filter (where x.status = 'Cleared') as cleared_count,
           count(*) filter (where x.status = 'Bounced') as bounced_count,
           min(x.cheque_date) filter (where x.status = 'Pending') as next_cheque_date
      from (select c.*, exists (select 1 from public.pdc_cheques r where r.replaces_id = c.id) as sup
              from public.pdc_cheques c where c.agreement_id = a.id) x) s
"""

AGREEMENT_SORT = {
    "end": "a.end_date",
    "start": "a.start_date",
    "branch": "b.name",
    "landlord": "lower(a.landlord)",
    "rent": "a.annual_rent",
}

CHEQUE_SELECT = """
select c.*, a.branch_id, b.name as branch_name, a.landlord, a.unit,
       rp.cheque_no as replaces_no, r.id as replaced_by_id, r.cheque_no as replaced_by_no,
       (r.id is not null) as superseded, pcl.full_name as cleared_by_name, pbo.full_name as bounced_by_name
  from public.pdc_cheques c
  join public.rental_agreements a on a.id = c.agreement_id
  join public.branches b on b.id = a.branch_id
  left join public.pdc_cheques rp on rp.id = c.replaces_id
  left join public.pdc_cheques r on r.replaces_id = c.id
  left join public.profiles pcl on pcl.user_id = c.cleared_by
  left join public.profiles pbo on pbo.user_id = c.bounced_by
"""

CHEQUE_SORT = {
    "date": "c.cheque_date",
    "number": "lower(c.cheque_no)",
    "amount": "c.amount",
    "branch": "b.name",
    "landlord": "lower(a.landlord)",
}


class RentalRepository(BaseRepository):
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

    def branch(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            "select id, name, is_active from public.branches where id = :i", {"i": id_}
        )

    def tracking_start(self) -> date | None:
        r = self._one("select as_of_date + 1 as d from public.opening_balances where id = 1")
        return r["d"] if r else None

    def record_history(self, table: str, record_id: uuid.UUID, limit: int = 100) -> list[Row]:
        return self._all(
            """select a.id, a.occurred_at, p.full_name as actor_name, a.action, a.table_name, a.record_id, a.reason,
                      a.old_values, a.new_values
                 from public.audit_log a left join public.profiles p on p.user_id = a.actor_user_id
                where a.table_name = :t and a.record_id = :r order by a.id desc limit :n""",
            {"t": table, "r": str(record_id), "n": limit},
        )

    # ---------------------------------------------------------------- agreements
    def agreement(self, id_: uuid.UUID, today: date, for_update: bool = False) -> Row | None:
        sql = AGREEMENT_SELECT + " where a.id = :i" + (" for update of a" if for_update else "")
        return self._one(sql, {"i": id_, "t": today})

    def agreements(
        self,
        today: date,
        q: str | None,
        branch_id: uuid.UUID | None,
        status: str | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
        upcoming_days: int | None = None,
    ) -> tuple[list[Row], int]:
        where: list[str] = ["1 = 1"]
        p: dict[str, Any] = {"t": today}
        if q:
            where.append(
                "(b.name ilike :q or a.landlord ilike :q or coalesce(a.unit, '') ilike :q)"
            )
            p["q"] = f"%{q}%"
        if branch_id:
            where.append("a.branch_id = :b")
            p["b"] = branch_id
        if status:
            where.append(f"{AGREEMENT_STATUS} = :st")
            p["st"] = status
        if upcoming_days is not None:
            where.append(
                "a.status = 'Active' and a.end_date between cast(:t as date) and cast(:t as date) + :ud"
            )
            p["ud"] = upcoming_days
        w = " and ".join(where)
        total = self._one(
            f"""select count(*) as n from public.rental_agreements a join public.branches b on b.id = a.branch_id
                 where {w}""",
            p,
        )
        order = AGREEMENT_SORT[sort] + (" desc" if desc else " asc") + ", lower(a.landlord), a.id"
        rows = self._all(
            f"{AGREEMENT_SELECT} where {w} order by {order} limit :lim offset :off",
            {**p, "lim": page_size, "off": (page - 1) * page_size},
        )
        return rows, int(total["n"]) if total else 0

    def agreement_summary(self, today: date) -> Row:
        r = self._one(
            f"""select
  count(*) filter (where {AGREEMENT_STATUS} in ('Active', 'Expiring', 'Scheduled')) as agreements_active,
  count(*) filter (where {AGREEMENT_STATUS} = 'Expiring') as expiring_30,
  count(*) filter (where {AGREEMENT_STATUS} = 'Expired') as expired_unrenewed,
  count(*) filter (where a.status = 'Active' and a.end_date between cast(:t as date) + 31
                                                              and cast(:t as date) + 90) as renewal_approaching,
  coalesce(sum(a.annual_rent) filter (where {AGREEMENT_STATUS} in ('Active', 'Expiring', 'Scheduled')), 0)
      as annual_rent_active
from public.rental_agreements a""",
            {"t": today},
        )
        assert r is not None
        return r

    def insert_agreement(self, v: Row) -> uuid.UUID:
        return self.session.execute(
            text(
                """insert into public.rental_agreements
                     (branch_id, landlord, unit, start_date, end_date, annual_rent, bank, cheque_count,
                      first_cheque_date, first_cheque_no, notes, renewed_from_id)
                   values (:branch_id, :landlord, :unit, :start_date, :end_date, :annual_rent, :bank, :cheque_count,
                           :first_cheque_date, :first_cheque_no, :notes, :renewed_from_id) returning id"""
            ),
            v,
        ).scalar_one()

    def update_agreement(self, id_: uuid.UUID, v: Row) -> None:
        self.session.execute(
            text(
                """update public.rental_agreements set branch_id = :branch_id, landlord = :landlord, unit = :unit,
                          start_date = :start_date, end_date = :end_date, notes = :notes where id = :id"""
            ),
            {**v, "id": id_},
        )

    def set_agreement_status(self, id_: uuid.UUID, status: str) -> None:
        self.session.execute(
            text("update public.rental_agreements set status = :s where id = :id"),
            {"s": status, "id": id_},
        )

    def renewal_chain(self, id_: uuid.UUID) -> list[Row]:
        """Every agreement linked to this one through renewed_from_id, oldest first."""
        return self._all(
            """with recursive up as (
                   select a.id, a.renewed_from_id, 0 as depth from public.rental_agreements a where a.id = :i
                   union all
                   select p.id, p.renewed_from_id, up.depth + 1 from public.rental_agreements p
                     join up on p.id = up.renewed_from_id),
               down as (
                   select a.id, 0 as depth from public.rental_agreements a where a.id = :i
                   union all
                   select n.id, down.depth + 1 from public.rental_agreements n join down on n.renewed_from_id = down.id)
               select a.id, a.start_date, a.end_date, a.annual_rent, a.cheque_count, a.status, a.renewed_from_id,
                      (a.id = :i) as is_current
                 from public.rental_agreements a
                where a.id in (select id from up union select id from down)
                order by a.start_date, a.created_at""",
            {"i": id_},
        )

    # ---------------------------------------------------------------- cheques
    def cheque(self, id_: uuid.UUID, for_update: bool = False) -> Row | None:
        sql = CHEQUE_SELECT + " where c.id = :i" + (" for update of c" if for_update else "")
        return self._one(sql, {"i": id_})

    def agreement_cheques(self, agreement_id: uuid.UUID) -> list[Row]:
        return self._all(
            CHEQUE_SELECT
            + " where c.agreement_id = :a order by c.cheque_date, c.cheque_no, c.created_at",
            {"a": agreement_id},
        )

    def cheques(
        self,
        today: date,
        q: str | None,
        branch_id: uuid.UUID | None,
        bank: str | None,
        status: str | None,
        view: str | None,
        date_from: date | None,
        date_to: date | None,
        agreement_id: uuid.UUID | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Row], int]:
        where: list[str] = ["1 = 1"]
        p: dict[str, Any] = {"t": today}
        if q:
            where.append("(c.cheque_no ilike :q or b.name ilike :q or a.landlord ilike :q)")
            p["q"] = f"%{q}%"
        if branch_id:
            where.append("a.branch_id = :b")
            p["b"] = branch_id
        if bank:
            where.append("c.bank = :bank")
            p["bank"] = bank
        if status:
            where.append("c.status = :st")
            p["st"] = status
        if agreement_id:
            where.append("c.agreement_id = :ag")
            p["ag"] = agreement_id
        if date_from:
            where.append("c.cheque_date >= :df")
            p["df"] = date_from
        if date_to:
            where.append("c.cheque_date <= :dt")
            p["dt"] = date_to
        if view == "overdue":
            where.append("c.status = 'Pending' and c.cheque_date < cast(:t as date)")
        elif view == "upcoming":
            where.append("c.status = 'Pending' and c.cheque_date >= cast(:t as date)")
        elif view == "bounced_open":
            where.append("c.status = 'Bounced' and r.id is null")
        w = " and ".join(where)
        join = """from public.pdc_cheques c join public.rental_agreements a on a.id = c.agreement_id
                  join public.branches b on b.id = a.branch_id left join public.pdc_cheques r on r.replaces_id = c.id"""
        total = self._one(f"select count(*) as n {join} where {w}", p)
        order = CHEQUE_SORT[sort] + (" desc" if desc else " asc") + ", lower(c.cheque_no), c.id"
        rows = self._all(
            f"{CHEQUE_SELECT} where {w} order by {order} limit :lim offset :off",
            {**p, "lim": page_size, "off": (page - 1) * page_size},
        )
        return rows, int(total["n"]) if total else 0

    def cheque_summary(self, today: date) -> Row:
        r = self._one(
            """select
  count(*) filter (where c.status = 'Pending') as pending_count,
  count(*) filter (where c.status = 'Pending' and c.cheque_date between cast(:t as date)
                                                                    and cast(:t as date) + 30) as due_30_count,
  count(*) filter (where c.status = 'Pending' and c.cheque_date < cast(:t as date)) as overdue_count,
  count(*) filter (where c.status = 'Cleared') as cleared_count,
  count(*) filter (where c.status = 'Bounced') as bounced_count,
  coalesce(sum(c.amount) filter (where c.status = 'Pending'), 0) as pending_amount,
  coalesce(sum(c.amount) filter (where c.status = 'Bounced'), 0) as bounced_amount,
  count(*) filter (where c.status = 'Bounced' and not exists (select 1 from public.pdc_cheques r
                                                               where r.replaces_id = c.id)) as bounced_unresolved_count,
  coalesce(sum(c.amount) filter (where c.status = 'Bounced' and not exists (select 1 from public.pdc_cheques r
                                                               where r.replaces_id = c.id)), 0)
      as bounced_unresolved_amount
from public.pdc_cheques c""",
            {"t": today},
        )
        assert r is not None
        return r

    def next_cheque(self, today: date) -> Row | None:
        return self._one(
            CHEQUE_SELECT
            + " where c.status = 'Pending' and c.cheque_date >= cast(:t as date) order by c.cheque_date, c.cheque_no limit 1",
            {"t": today},
        )

    def insert_cheque(self, v: Row) -> uuid.UUID:
        return self.session.execute(
            text(
                """insert into public.pdc_cheques (agreement_id, cheque_no, bank, cheque_date, amount, status, notes,
                                                   replaces_id, client_key)
                   values (:agreement_id, :cheque_no, :bank, :cheque_date, :amount, 'Pending', :notes,
                           :replaces_id, :client_key) returning id"""
            ),
            {"replaces_id": None, "client_key": None, "notes": None, **v},
        ).scalar_one()

    def update_pending_cheque(self, id_: uuid.UUID, v: Row) -> None:
        self.session.execute(
            text(
                """update public.pdc_cheques set cheque_no = :cheque_no, cheque_date = :cheque_date, bank = :bank,
                          notes = :notes where id = :id"""
            ),
            {**v, "id": id_},
        )

    def mark_cleared(self, id_: uuid.UUID, cleared_on: date) -> None:
        self.session.execute(
            text(
                "update public.pdc_cheques set status = 'Cleared', cleared_on = :d where id = :id"
            ),
            {"d": cleared_on, "id": id_},
        )

    def mark_bounced(self, id_: uuid.UUID, bounced_on: date) -> None:
        self.session.execute(
            text(
                "update public.pdc_cheques set status = 'Bounced', bounced_on = :d where id = :id"
            ),
            {"d": bounced_on, "id": id_},
        )

    def bank_balance(self, bank: str, as_of: date) -> Any:
        r = self._one(
            "select enbd_now, adcb_now from public.app_balances(cast(:d as date))", {"d": as_of}
        )
        assert r is not None
        return r["enbd_now" if bank == "ENBD" else "adcb_now"]

    # ---------------------------------------------------------------- alerts (one row per record + condition)
    def alert_rows(self, today: date) -> list[Row]:
        return self._all(
            """
select 'rental_expired' as kind, a.id as record_id, a.id as agreement_id, b.name as branch_name, a.landlord,
       null::text as cheque_no, null::numeric as amount, null::text as bank, a.end_date as due
  from public.rental_agreements a join public.branches b on b.id = a.branch_id
 where a.status = 'Active' and a.end_date < cast(:t as date)
union all
select 'rental_ending', a.id, a.id, b.name, a.landlord, null, null, null, a.end_date
  from public.rental_agreements a join public.branches b on b.id = a.branch_id
 where a.status = 'Active' and a.end_date between cast(:t as date) and cast(:t as date) + 30
union all
select 'rental_renewal_upcoming', a.id, a.id, b.name, a.landlord, null, null, null, a.end_date
  from public.rental_agreements a join public.branches b on b.id = a.branch_id
 where a.status = 'Active' and a.end_date between cast(:t as date) + 31 and cast(:t as date) + 90
union all
select 'cheque_overdue', c.id, c.agreement_id, b.name, a.landlord, c.cheque_no, c.amount, c.bank, c.cheque_date
  from public.pdc_cheques c join public.rental_agreements a on a.id = c.agreement_id
  join public.branches b on b.id = a.branch_id
 where c.status = 'Pending' and c.cheque_date < cast(:t as date)
union all
select 'cheque_due_7', c.id, c.agreement_id, b.name, a.landlord, c.cheque_no, c.amount, c.bank, c.cheque_date
  from public.pdc_cheques c join public.rental_agreements a on a.id = c.agreement_id
  join public.branches b on b.id = a.branch_id
 where c.status = 'Pending' and c.cheque_date between cast(:t as date) and cast(:t as date) + 7
union all
select 'cheque_due_30', c.id, c.agreement_id, b.name, a.landlord, c.cheque_no, c.amount, c.bank, c.cheque_date
  from public.pdc_cheques c join public.rental_agreements a on a.id = c.agreement_id
  join public.branches b on b.id = a.branch_id
 where c.status = 'Pending' and c.cheque_date between cast(:t as date) + 8 and cast(:t as date) + 30
union all
select 'cheque_bounced', c.id, c.agreement_id, b.name, a.landlord, c.cheque_no, c.amount, c.bank, c.bounced_on
  from public.pdc_cheques c join public.rental_agreements a on a.id = c.agreement_id
  join public.branches b on b.id = a.branch_id
 where c.status = 'Bounced' and not exists (select 1 from public.pdc_cheques r where r.replaces_id = c.id)
order by 9 asc, 1, 6""",
            {"t": today},
        )
