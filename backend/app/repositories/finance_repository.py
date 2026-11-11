"""Step 8 data access (queries only; every rule lives in the services). Runs as `authenticated` under RLS."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository

Row = dict[str, Any]
FINANCE_LOCK = (
    80801  # one advisory lock serialises every balance-affecting write (race-safe negative checks)
)
DB_ACCOUNT = {"Cash": "Cash received", "ENBD": "ENBD", "ADCB": "ADCB"}
API_ACCOUNT = {"Cash received": "Cash", "ENBD": "ENBD", "ADCB": "ADCB"}


class FinanceRepository(BaseRepository):
    def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        return [dict(r) for r in self.session.execute(text(sql), params or {}).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any] | None = None) -> Row | None:
        r = self.session.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None

    def lock(self) -> None:
        self.session.execute(text("select pg_advisory_xact_lock(:k)"), {"k": FINANCE_LOCK})

    def set_reason(self, reason: str | None) -> None:
        self.session.execute(
            text("select set_config('app.audit_reason', :r, true)"), {"r": reason or ""}
        )

    # ---- opening balances --------------------------------------------------------------------------------
    def opening(self) -> Row | None:
        return self._one(
            """select o.*, p.full_name as updated_by_name from public.opening_balances o
                 left join public.profiles p on p.user_id = o.updated_by where o.id = 1"""
        )

    def opening_branch_cash(self) -> list[Row]:
        return self._all(
            """select b.id as branch_id, b.name as branch_name, coalesce(c.amount, 0) as amount
                 from public.branches b left join public.opening_branch_cash c on c.branch_id = b.id
                order by b.sort_order, b.name"""
        )

    def supplier_openings(self) -> list[Row]:
        return self._all(
            "select id as supplier_id, name as supplier_name, amount_owed as amount from public.suppliers order by lower(name)"
        )

    def flows_exist(self) -> bool:
        r = self._one(
            """select (exists (select 1 from public.daily_reports) or exists (select 1 from public.head_office_expenses)
                    or exists (select 1 from public.supplier_entries) or exists (select 1 from public.pos_settlements)
                    or exists (select 1 from public.cash_transfers)) as x"""
        )
        return bool(r and r["x"])

    def upsert_opening(self, v: dict[str, Any]) -> None:
        self.session.execute(
            text(
                """insert into public.opening_balances
                     (id, as_of_date, receipts_bank, enbd_balance, adcb_balance, pos_pending, savings_brought_forward, updated_by)
                   values (1, :as_of_date, :receipts_bank, :enbd_balance, :adcb_balance, :pos_pending,
                           :savings_brought_forward, auth.uid())
                   on conflict (id) do update set as_of_date = excluded.as_of_date, receipts_bank = excluded.receipts_bank,
                     enbd_balance = excluded.enbd_balance, adcb_balance = excluded.adcb_balance,
                     pos_pending = excluded.pos_pending, savings_brought_forward = excluded.savings_brought_forward"""
            ),
            v,
        )

    def upsert_branch_cash(self, branch_id: uuid.UUID, amount: Decimal) -> None:
        self.session.execute(
            text(
                """insert into public.opening_branch_cash (branch_id, amount, updated_by) values (:b, :a, auth.uid())
                   on conflict (branch_id) do update set amount = excluded.amount
                   where public.opening_branch_cash.amount is distinct from excluded.amount"""
            ),
            {"b": branch_id, "a": amount},
        )

    def set_supplier_opening(self, supplier_id: uuid.UUID, amount: Decimal) -> None:
        self.session.execute(
            text(
                "update public.suppliers set amount_owed = :a where id = :i and amount_owed is distinct from :a"
            ),
            {"a": amount, "i": supplier_id},
        )

    def opening_history(self, limit: int = 100) -> list[Row]:
        return self._all(
            """select a.id, a.occurred_at, p.full_name as actor_name, a.action, a.table_name, a.record_id, a.reason,
                      a.old_values, a.new_values
                 from public.audit_log a left join public.profiles p on p.user_id = a.actor_user_id
                where a.table_name in ('opening_balances', 'opening_branch_cash')
                   or (a.table_name = 'suppliers' and a.action = 'UPDATE'
                       and a.old_values ->> 'amount_owed' is distinct from a.new_values ->> 'amount_owed')
                order by a.id desc limit :n""",
            {"n": limit},
        )

    def record_history(self, table: str, record_id: uuid.UUID, limit: int = 50) -> list[Row]:
        return self._all(
            """select a.id, a.occurred_at, p.full_name as actor_name, a.action, a.table_name, a.record_id, a.reason,
                      a.old_values, a.new_values
                 from public.audit_log a left join public.profiles p on p.user_id = a.actor_user_id
                where a.table_name = :t and a.record_id = :r order by a.id desc limit :n""",
            {"t": table, "r": str(record_id), "n": limit},
        )

    # ---- balances and ledger ----------------------------------------------------------------------------
    def balances(self, as_of: date) -> Row:
        r = self._one("select * from public.app_balances(cast(:d as date))", {"d": as_of})
        assert r is not None
        return r

    def branch_cash(self, as_of: date) -> list[Row]:
        return self._all("select * from public.app_branch_cash(cast(:d as date))", {"d": as_of})

    def ledger_totals(self, d_from: date, d_to: date) -> dict[str, Row]:
        rows = self._all(
            """select account, coalesce(sum(amount) filter (where amount > 0), 0) as incoming,
                      coalesce(-sum(amount) filter (where amount < 0), 0) as outgoing
                 from public.app_cash_bank_ledger(cast(:f as date), cast(:t as date)) group by account""",
            {"f": d_from, "t": d_to},
        )
        return {r["account"]: r for r in rows}

    _LEDGER_WHERE = """ (cast(:acc as text) is null or account = cast(:acc as text))
          and (cast(:b as uuid) is null or branch_id = cast(:b as uuid))
          and (cast(:ty as text) is null or txn_type = cast(:ty as text))"""

    def ledger_page(
        self,
        d_from: date,
        d_to: date,
        account: str | None,
        branch: uuid.UUID | None,
        txn_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int, Row]:
        p = {"f": d_from, "t": d_to, "acc": account, "b": branch, "ty": txn_type}
        src = (
            "from public.app_cash_bank_ledger(cast(:f as date), cast(:t as date)) where"
            + self._LEDGER_WHERE
        )
        rows = self._all(
            f"select * {src} order by txn_date desc, created_at desc, txn_type limit :lim offset :off",
            {**p, "lim": limit, "off": offset},
        )
        agg = self._one(
            f"""select count(*) as n, coalesce(sum(amount) filter (where amount > 0), 0) as inc,
                       coalesce(-sum(amount) filter (where amount < 0), 0) as outg {src}""",
            p,
        )
        assert agg is not None
        return rows, int(agg["n"]), agg

    # ---- transfers / POS settlements ---------------------------------------------------------------------
    def insert_transfer(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.cash_transfers (transfer_date, from_account, to_account, branch_id, amount, reference, note, client_key)
               values (:transfer_date, :from_account, :to_account, :branch_id, :amount, :reference, :note, :client_key)
               returning id""",
            v,
        )
        assert r is not None
        return r["id"]

    def transfer(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            """select t.*, b.name as branch_name from public.cash_transfers t
                 left join public.branches b on b.id = t.branch_id where t.id = :i""",
            {"i": id_},
        )

    def transfers(self, limit: int = 100) -> list[Row]:
        return self._all(
            """select t.*, b.name as branch_name from public.cash_transfers t
                 left join public.branches b on b.id = t.branch_id order by t.transfer_date desc, t.created_at desc limit :n""",
            {"n": limit},
        )

    def insert_settlement(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.pos_settlements (settlement_date, bank, amount, reference, note, client_key)
               values (:settlement_date, :bank, :amount, :reference, :note, :client_key) returning id""",
            v,
        )
        assert r is not None
        return r["id"]

    def settlement(self, id_: uuid.UUID) -> Row | None:
        return self._one("select * from public.pos_settlements where id = :i", {"i": id_})

    def settlements(self, limit: int = 100) -> list[Row]:
        return self._all(
            "select * from public.pos_settlements order by settlement_date desc, created_at desc limit :n",
            {"n": limit},
        )

    def void_ledger(self, fn: str, id_: uuid.UUID, reason: str) -> None:
        assert fn in {
            "void_cash_transfer",
            "void_pos_settlement",
            "void_supplier_entry",
            "void_head_office_expense",
        }
        self.session.execute(text(f"select public.{fn}(:i, :r)"), {"i": id_, "r": reason})  # noqa: S608 - fixed allow-list

    # ---- expenses ----------------------------------------------------------------------------------------
    def categories(self) -> list[Row]:
        return self._all(
            "select id, name from public.expense_categories where is_active order by name"
        )

    def category(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            "select id, name, is_active from public.expense_categories where id = :i", {"i": id_}
        )

    def branch(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            "select id, name, is_active from public.branches where id = :i", {"i": id_}
        )

    def insert_expense(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.head_office_expenses
                 (expense_date, branch_id, category_id, amount, paid_from, note, is_saving, client_key, corrects_id)
               values (:expense_date, :branch_id, :category_id, :amount, :paid_from, :note, :is_saving, :client_key, :corrects_id)
               returning id""",
            v,
        )
        assert r is not None
        return r["id"]

    _EXP_SELECT = """select h.id, h.expense_date, h.branch_id, b.name as branch_name, h.category_id, c.name as category,
                            h.amount, h.paid_from, h.note, h.is_saving, (h.voided_at is not null) as voided, h.void_reason,
                            h.corrects_id, h.created_at, p.full_name as created_by_name
                       from public.head_office_expenses h
                       join public.expense_categories c on c.id = h.category_id
                       left join public.branches b on b.id = h.branch_id
                       left join public.profiles p on p.user_id = h.created_by"""

    def expense(self, id_: uuid.UUID) -> Row | None:
        return self._one(self._EXP_SELECT + " where h.id = :i", {"i": id_})

    def expenses_page(self, f: dict[str, Any], limit: int, offset: int) -> tuple[list[Row], Row]:
        where = """ where (cast(:d_from as date) is null or h.expense_date >= cast(:d_from as date))
              and (cast(:d_to as date) is null or h.expense_date <= cast(:d_to as date))
              and (cast(:branch as uuid) is null or h.branch_id = cast(:branch as uuid))
              and (not :all_only or h.branch_id is null)
              and (cast(:cat as uuid) is null or h.category_id = cast(:cat as uuid))
              and (cast(:pf as text) is null or h.paid_from = cast(:pf as text))
              and (cast(:sav as boolean) is null or h.is_saving = cast(:sav as boolean))
              and (:voided or h.voided_at is null)"""
        rows = self._all(
            self._EXP_SELECT
            + where
            + " order by h.expense_date desc, h.created_at desc limit :lim offset :off",
            {**f, "lim": limit, "off": offset},
        )
        agg = self._one(
            """select count(*) as n, coalesce(sum(h.amount) filter (where h.voided_at is null), 0) as total,
                      coalesce(sum(h.amount) filter (where h.voided_at is null and h.is_saving), 0) as savings,
                      count(*) filter (where h.voided_at is null) as active
                 from public.head_office_expenses h"""
            + where,
            f,
        )
        assert agg is not None
        return rows, agg

    def set_saving(self, id_: uuid.UUID, is_saving: bool) -> int:
        return self.session.execute(
            text(
                "update public.head_office_expenses set is_saving = :s where id = :i and voided_at is null"
            ),
            {"s": is_saving, "i": id_},
        ).rowcount  # type: ignore[attr-defined,no-any-return]

    # ---- suppliers ---------------------------------------------------------------------------------------
    _SUP_SELECT = """select s.id, s.name, s.category, s.payment_terms, s.notes, s.is_active, s.created_at,
                            v.opening_outstanding, v.new_dues, v.payments as total_paid, v.outstanding
                       from public.suppliers s join public.v_supplier_outstanding v on v.supplier_id = s.id"""

    def supplier(self, id_: uuid.UUID) -> Row | None:
        return self._one(self._SUP_SELECT + " where s.id = :i", {"i": id_})

    def suppliers_page(
        self,
        search: str | None,
        status: str,
        owing_only: bool,
        sort: str,
        desc: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int]:
        order = {
            "name": "lower(s.name)",
            "outstanding": "v.outstanding",
            "paid": "v.payments",
            "created": "s.created_at",
        }[sort]
        where = """ where (cast(:q as text) is null or s.name ilike '%' || cast(:q as text) || '%'
                           or coalesce(s.category, '') ilike '%' || cast(:q as text) || '%')
              and (:st = 'all' or (:st = 'active' and s.is_active) or (:st = 'inactive' and not s.is_active))
              and (not :owing or v.outstanding > 0)"""
        p = {"q": search, "st": status, "owing": owing_only}
        rows = self._all(
            f"{self._SUP_SELECT}{where} order by {order} {'desc' if desc else 'asc'}, lower(s.name) limit :lim offset :off",  # noqa: S608
            {**p, "lim": limit, "off": offset},
        )
        n = self._one(
            "select count(*) as n from public.suppliers s join public.v_supplier_outstanding v on v.supplier_id = s.id"
            + where,
            p,
        )
        assert n is not None
        return rows, int(n["n"])

    def supplier_summary(self) -> Row:
        r = self._one(
            """select count(*) as total_suppliers, coalesce(sum(outstanding), 0) as total_outstanding,
                      coalesce(sum(payments), 0) as total_paid, count(*) filter (where outstanding > 0) as with_outstanding
                 from public.v_supplier_outstanding"""
        )
        assert r is not None
        return r

    def insert_supplier(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.suppliers (name, category, payment_terms, notes, is_active, amount_owed)
               values (:name, :category, :payment_terms, :notes, :is_active, :opening) returning id""",
            v,
        )
        assert r is not None
        return r["id"]

    def update_supplier(self, id_: uuid.UUID, v: dict[str, Any]) -> int:
        return self.session.execute(
            text(
                """update public.suppliers set name = :name, category = :category, payment_terms = :payment_terms,
                          notes = :notes, is_active = :is_active where id = :i"""
            ),
            {**v, "i": id_},
        ).rowcount  # type: ignore[attr-defined,no-any-return]

    def insert_entry(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.supplier_entries
                 (supplier_id, entry_date, kind, amount, paid_from, branch_id, reference, note, client_key)
               values (:supplier_id, :entry_date, :kind, :amount, :paid_from, :branch_id, :reference, :note, :client_key)
               returning id""",
            v,
        )
        assert r is not None
        return r["id"]

    _ENT_SELECT = """select e.id, e.supplier_id, s.name as supplier_name, e.entry_date, e.kind, e.amount, e.paid_from,
                            b.name as branch_name, e.reference, e.note, (e.voided_at is not null) as voided, e.void_reason,
                            e.created_at, p.full_name as created_by_name
                       from public.supplier_entries e join public.suppliers s on s.id = e.supplier_id
                       left join public.branches b on b.id = e.branch_id
                       left join public.profiles p on p.user_id = e.created_by"""

    def entry(self, id_: uuid.UUID) -> Row | None:
        return self._one(self._ENT_SELECT + " where e.id = :i", {"i": id_})

    def entries_page(
        self,
        supplier_id: uuid.UUID,
        kind: str | None,
        d_from: date | None,
        d_to: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Row], int]:
        where = """ where e.supplier_id = :s and (cast(:k as text) is null or e.kind = cast(:k as text))
              and (cast(:f as date) is null or e.entry_date >= cast(:f as date))
              and (cast(:t as date) is null or e.entry_date <= cast(:t as date))"""
        p = {"s": supplier_id, "k": kind, "f": d_from, "t": d_to}
        rows = self._all(
            self._ENT_SELECT
            + where
            + " order by e.entry_date desc, e.created_at desc limit :lim offset :off",
            {**p, "lim": limit, "off": offset},
        )
        n = self._one("select count(*) as n from public.supplier_entries e" + where, p)
        assert n is not None
        return rows, int(n["n"])

    def negative_suppliers(self) -> int:
        r = self._one(
            "select count(*) as n from public.v_supplier_outstanding where outstanding < 0"
        )
        assert r is not None
        return int(r["n"])
