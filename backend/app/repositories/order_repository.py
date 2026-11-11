import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository

Row = dict[str, Any]

ORDER_SELECT = """
select o.id, o.order_no, o.customer_id, c.name as customer_name, c.mobile, c.area, o.branch_id, b.name as branch_name,
       sc.name as category, o.service_type, o.status, o.payment_status, o.order_date, o.pickup_at, o.pickup_address,
       o.delivery_at, o.delivery_address, o.final_payable, o.amount_collected,
       (o.final_payable - o.amount_collected) as outstanding
  from public.orders o
  join public.customers c on c.id = o.customer_id
  join public.branches b on b.id = o.branch_id
  join public.service_categories sc on sc.id = o.category_id"""

SORTS = {
    "order_no": "o.order_no",
    "order_date": "o.order_date",
    "pickup": "o.pickup_at",
    "delivery": "o.delivery_at",
    "customer": "lower(c.name)",
    "status": "o.status",
    "amount": "o.final_payable",
    "outstanding": "(o.final_payable - o.amount_collected)",
    "created": "o.created_at",
}

# Operational views. :t0/:t1 = the chosen day (Dubai) as a timestamp range, :now0 = start of the REAL current Dubai day.
VIEWS = {
    "pickups_today": "o.pickup_at >= :t0 and o.pickup_at < :t1 and o.status <> 'Cancelled'",
    "deliveries_today": "o.delivery_at >= :t0 and o.delivery_at < :t1 and o.status <> 'Cancelled'",
    "pending_pickups": "o.status in ('New', 'Scheduled') and o.pickup_at is not null",
    "overdue_pickups": "o.status in ('New', 'Scheduled') and o.pickup_at is not null and o.pickup_at < :now0",
    "processing": "o.status = 'Processing'",
    "ready": "o.status = 'Ready'",
    "out_for_delivery": "o.status = 'Out for Delivery'",
    "overdue_deliveries": "o.status not in ('Delivered', 'Cancelled') and o.delivery_at < :now0",
    "incomplete": (
        "o.status not in ('Delivered', 'Cancelled') and (o.delivery_address is null "
        "or (o.pickup_at is null and o.status in ('New', 'Scheduled')))"
    ),
    "recent": "true",
}


@dataclass(frozen=True)
class OrderFilter:
    branch_id: uuid.UUID | None = None
    q: str | None = None
    status: str | None = None
    payment_status: str | None = None
    category_id: uuid.UUID | None = None
    service_type: str | None = None
    area: str | None = None
    order_from: date | None = None
    order_to: date | None = None
    pickup_bounds: tuple[datetime, datetime] | None = None
    delivery_bounds: tuple[datetime, datetime] | None = None
    customer_id: uuid.UUID | None = None
    view: str | None = None
    day_bounds: tuple[datetime, datetime] | None = None
    now0: datetime | None = None


def phone_digits(q: str) -> str | None:
    """Digits to match inside a stored +E.164 number, only when the search text looks like a phone number (no letters).
    A leading local 0 is dropped (0501234567 matches +971501234567)."""
    if any(ch.isalpha() for ch in q):
        return None
    digits = "".join(ch for ch in q if ch.isdigit()).lstrip("0")
    return digits if len(digits) >= 3 else None


def where(f: OrderFilter) -> tuple[str, dict[str, Any]]:
    parts: list[str] = []
    p: dict[str, Any] = {}

    def add(cond: str, **kw: Any) -> None:
        parts.append(cond)
        p.update(kw)

    if f.branch_id:
        add("o.branch_id = :branch", branch=f.branch_id)
    if f.customer_id:
        add("o.customer_id = :cust", cust=f.customer_id)
    if f.q:
        cond = "(o.order_no ilike :qlike or c.name ilike :qlike or c.mobile ilike :qlike"
        if digits := phone_digits(f.q):
            cond += " or regexp_replace(c.mobile, '[^0-9]', '', 'g') like :qdigits"
            p["qdigits"] = f"%{digits}%"
        add(cond + ")", qlike=f"%{f.q.strip()}%")
    if f.status:
        add("o.status = :status", status=f.status)
    if f.payment_status:
        add("o.payment_status = :pstat", pstat=f.payment_status)
    if f.category_id:
        add("o.category_id = :cat", cat=f.category_id)
    if f.service_type:
        add("o.service_type = :stype", stype=f.service_type)
    if f.area:
        add("c.area ilike :area", area=f"%{f.area.strip()}%")
    if f.order_from:
        add("o.order_date >= :ofrom", ofrom=f.order_from)
    if f.order_to:
        add("o.order_date <= :oto", oto=f.order_to)
    if f.pickup_bounds:
        add(
            "o.pickup_at >= :pk0 and o.pickup_at < :pk1",
            pk0=f.pickup_bounds[0],
            pk1=f.pickup_bounds[1],
        )
    if f.delivery_bounds:
        add(
            "o.delivery_at >= :dl0 and o.delivery_at < :dl1",
            dl0=f.delivery_bounds[0],
            dl1=f.delivery_bounds[1],
        )
    if f.view:
        add(VIEWS[f.view])
        if f.day_bounds:
            p.update(t0=f.day_bounds[0], t1=f.day_bounds[1])
        if f.now0:
            p["now0"] = f.now0
    return (" where " + " and ".join(parts)) if parts else "", p


class OrderRepository(BaseRepository):
    def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        return [dict(r) for r in self.session.execute(text(sql), params or {}).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any] | None = None) -> Row | None:
        r = self.session.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None

    def set_reason(self, reason: str | None, note: str | None = None) -> None:
        self.session.execute(
            text("select set_config('app.audit_reason', :r, true)"), {"r": reason or ""}
        )
        self.session.execute(
            text("select set_config('app.status_note', :r, true)"), {"r": note or ""}
        )

    # ---- lookups ---------------------------------------------------------------------------------------
    def branch(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            "select id, name, is_active from public.branches where id = :i", {"i": id_}
        )

    def categories(self) -> list[Row]:
        return self._all(
            "select id, name, is_active from public.service_categories order by sort_order, name"
        )

    def category(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            "select id, name, is_active from public.service_categories where id = :i", {"i": id_}
        )

    # ---- customers -------------------------------------------------------------------------------------
    CUSTOMER_SELECT = """
select c.id, c.branch_id, b.name as branch_name, c.name, c.mobile, c.whatsapp, c.address, c.area, c.notes, c.created_at,
       coalesce(a.n, 0) as order_count, coalesce(a.billed, 0) as total_billed,
       coalesce(a.owed, 0) as outstanding, a.last_date as last_order_date
  from public.customers c
  join public.branches b on b.id = c.branch_id
  left join lateral (
      select count(*) filter (where o.status <> 'Cancelled') as n,
             coalesce(sum(o.final_payable) filter (where o.status <> 'Cancelled'), 0) as billed,
             coalesce(sum(o.final_payable - o.amount_collected) filter (where o.status <> 'Cancelled'), 0) as owed,
             max(o.order_date) as last_date
        from public.orders o where o.customer_id = c.id) a on true"""

    def customer(self, id_: uuid.UUID) -> Row | None:
        return self._one(self.CUSTOMER_SELECT + " where c.id = :i", {"i": id_})

    def customer_by_mobile(self, branch_id: uuid.UUID, mobile: str) -> Row | None:
        return self._one(
            "select id, name from public.customers where branch_id = :b and mobile = :m",
            {"b": branch_id, "m": mobile},
        )

    def list_customers(
        self, branch_id: uuid.UUID | None, q: str | None, limit: int, offset: int
    ) -> tuple[list[Row], int]:
        conds: list[str] = []
        p: dict[str, Any] = {"lim": limit, "off": offset}
        if branch_id:
            conds.append("c.branch_id = :b")
            p["b"] = branch_id
        if q:
            cond = "(c.name ilike :ql or c.mobile ilike :ql or coalesce(c.whatsapp, '') ilike :ql"
            if digits := phone_digits(q):
                cond += " or regexp_replace(c.mobile, '[^0-9]', '', 'g') like :qd"
                p["qd"] = f"%{digits}%"
            conds.append(cond + ")")
            p["ql"] = f"%{q.strip()}%"
        w = (" where " + " and ".join(conds)) if conds else ""
        total = self._one(f"select count(*) as n from public.customers c{w}", p)  # noqa: S608
        rows = self._all(
            f"{self.CUSTOMER_SELECT}{w} order by lower(c.name), c.created_at limit :lim offset :off",  # noqa: S608
            p,
        )
        return rows, int(total["n"]) if total else 0

    def insert_customer(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.customers (branch_id, name, mobile, whatsapp, address, area, notes)
               values (:branch_id, :name, :mobile, :whatsapp, :address, :area, :notes) returning id""",
            v,
        )
        assert r is not None
        return r["id"]  # type: ignore[no-any-return]

    def update_customer(self, id_: uuid.UUID, v: dict[str, Any]) -> None:
        self.session.execute(
            text(
                """update public.customers set name = :name, mobile = :mobile, whatsapp = :whatsapp,
                          address = :address, area = :area, notes = :notes where id = :id"""
            ),
            {**v, "id": id_},
        )

    # ---- orders ----------------------------------------------------------------------------------------
    def list_orders(
        self, f: OrderFilter, sort: str, desc: bool, limit: int | None, offset: int = 0
    ) -> tuple[list[Row], int]:
        w, p = where(f)
        total = self._one(
            "select count(*) as n from public.orders o join public.customers c on c.id = o.customer_id"
            + w,  # noqa: S608
            p,
        )
        col = SORTS.get(sort, SORTS["created"])
        direction = "desc" if desc else "asc"
        sql = f"{ORDER_SELECT}{w} order by {col} {direction} nulls last, o.order_no desc"  # noqa: S608
        if limit is not None:
            sql += " limit :lim offset :off"
            p = {**p, "lim": limit, "off": offset}
        return self._all(sql, p), int(total["n"]) if total else 0

    def count(self, f: OrderFilter) -> int:
        w, p = where(f)
        r = self._one(
            "select count(*) as n from public.orders o join public.customers c on c.id = o.customer_id"
            + w,  # noqa: S608
            p,
        )
        return int(r["n"]) if r else 0

    def order_row(self, id_: uuid.UUID) -> Row | None:
        return self._one(ORDER_SELECT + " where o.id = :i", {"i": id_})

    def order_full(self, id_: uuid.UUID, for_update: bool = False) -> Row | None:
        return self._one(
            f"""select o.*, c.whatsapp as customer_whatsapp, c.address as customer_address,
                       cr.full_name as created_by_name, up.full_name as updated_by_name
                  from public.orders o
                  join public.customers c on c.id = o.customer_id
                  left join public.profiles cr on cr.user_id = o.created_by
                  left join public.profiles up on up.user_id = o.updated_by
                 where o.id = :i{" for update of o" if for_update else ""}""",  # noqa: S608
            {"i": id_},
        )

    def order_id_by_key(self, key: uuid.UUID) -> uuid.UUID | None:
        r = self._one("select id from public.orders where client_key = :k", {"k": key})
        return r["id"] if r else None  # type: ignore[no-any-return]

    def insert_order(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.orders (customer_id, branch_id, order_date, category_id, service_type, notes,
                      pickup_at, pickup_address, delivery_at, delivery_address, order_total, discount, service_fee,
                      client_key)
               values (:customer_id, :branch_id, :order_date, :category_id, :service_type, :notes,
                      :pickup_at, :pickup_address, :delivery_at, :delivery_address, :order_total, :discount, :service_fee,
                      :client_key)
               returning id""",
            v,
        )
        assert r is not None
        return r["id"]  # type: ignore[no-any-return]

    def update_order(self, id_: uuid.UUID, v: dict[str, Any]) -> None:
        self.session.execute(
            text(
                """update public.orders set category_id = :category_id, service_type = :service_type, notes = :notes,
                          pickup_at = :pickup_at, pickup_address = :pickup_address, delivery_at = :delivery_at,
                          delivery_address = :delivery_address, order_total = :order_total, discount = :discount,
                          service_fee = :service_fee where id = :id"""
            ),
            {**v, "id": id_},
        )

    def set_status(self, id_: uuid.UUID, status: str, cancel_reason: str | None = None) -> None:
        self.session.execute(
            text("update public.orders set status = :s, cancel_reason = :r where id = :i"),
            {"s": status, "i": id_, "r": cancel_reason},
        )

    # ---- payments --------------------------------------------------------------------------------------
    def insert_payment(self, v: dict[str, Any]) -> uuid.UUID:
        r = self._one(
            """insert into public.order_payments (order_id, payment_date, amount, method, reference, note, client_key)
               values (:order_id, coalesce(:payment_date, app.dubai_today()), :amount, :method, :reference, :note, :client_key)
               returning id""",
            v,
        )
        assert r is not None
        return r["id"]  # type: ignore[no-any-return]

    def payment_by_key(self, key: uuid.UUID) -> Row | None:
        return self._one(
            "select id, order_id from public.order_payments where client_key = :k", {"k": key}
        )

    def payments(self, order_id: uuid.UUID) -> list[Row]:
        return self._all(
            """select p.id, p.payment_date, p.amount, p.method, p.reference, p.note, p.created_at,
                      u.full_name as recorded_by
                 from public.order_payments p left join public.profiles u on u.user_id = p.created_by
                where p.order_id = :o order by p.payment_date, p.created_at""",
            {"o": order_id},
        )

    def history(self, order_id: uuid.UUID) -> list[Row]:
        return self._all(
            """select h.id, h.from_status, h.to_status, u.full_name as changed_by, h.changed_at, h.note
                 from public.order_status_history h left join public.profiles u on u.user_id = h.changed_by
                where h.order_id = :o order by h.id""",
            {"o": order_id},
        )

    def payment_summary(self, branch_id: uuid.UUID | None, d_from: date, d_to: date) -> list[Row]:
        return self._all(
            """select p.method, count(*) as n, coalesce(sum(p.amount), 0) as total
                 from public.order_payments p
                where p.payment_date between :f and :t and (cast(:b as uuid) is null or p.branch_id = cast(:b as uuid))
                group by p.method order by p.method""",
            {"f": d_from, "t": d_to, "b": branch_id},
        )

    # ---- dashboard + report aggregates -----------------------------------------------------------------
    def revenue_between(self, branch_id: uuid.UUID | None, d_from: date, d_to: date) -> Decimal:
        r = self._one(
            """select coalesce(sum(final_payable), 0) as v from public.orders
                where status <> 'Cancelled' and order_date between :f and :t
                  and (cast(:b as uuid) is null or branch_id = cast(:b as uuid))""",
            {"f": d_from, "t": d_to, "b": branch_id},
        )
        return Decimal(str(r["v"])) if r else Decimal(0)

    def outstanding_total(self, f: OrderFilter) -> Decimal:
        w, p = where(f)
        extra = " and " if w else " where "
        r = self._one(
            "select coalesce(sum(o.final_payable - o.amount_collected), 0) as v from public.orders o "  # noqa: S608
            "join public.customers c on c.id = o.customer_id"
            + w
            + extra
            + "o.status <> 'Cancelled'",
            p,
        )
        return Decimal(str(r["v"])) if r else Decimal(0)

    def grouped(self, f: OrderFilter, expr: str, label: str) -> list[Row]:
        """Aggregates per `expr` (a trusted SQL fragment chosen by the service, never user text)."""
        w, p = where(f)
        return self._all(
            f"""select {expr} as {label},
                       count(*) as orders,
                       count(*) filter (where o.status = 'Delivered') as completed,
                       count(*) filter (where o.status = 'Cancelled') as cancelled,
                       count(*) filter (where o.service_type = 'Express' and o.status <> 'Cancelled') as express,
                       count(*) filter (where o.service_type = 'Standard' and o.status <> 'Cancelled') as standard,
                       coalesce(sum(o.final_payable) filter (where o.status <> 'Cancelled'), 0) as revenue,
                       coalesce(sum(o.amount_collected) filter (where o.status <> 'Cancelled'), 0) as collected,
                       coalesce(sum(o.final_payable - o.amount_collected) filter (where o.status <> 'Cancelled'), 0) as outstanding,
                       coalesce(sum(o.amount_collected) filter (where o.status = 'Cancelled'), 0) as held_cancelled
                  from public.orders o
                  join public.customers c on c.id = o.customer_id
                  join public.branches b on b.id = o.branch_id
                  join public.service_categories sc on sc.id = o.category_id
                 {w} group by 1 order by 1""",  # noqa: S608
            p,
        )
