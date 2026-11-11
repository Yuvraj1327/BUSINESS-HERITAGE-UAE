import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository

Row = dict[str, Any]

SELECT = """select a.*, case when a.resolved_at is not null then 'resolved'
                             when a.acknowledged_at is not null then 'acknowledged'
                             when a.read_at is not null then 'read' else 'unread' end as status
              from public.alerts a"""

SEVERITY_ORDER = "case a.severity when 'critical' then 0 when 'warning' then 1 else 2 end"
ACTIVE = "a.resolved_at is null and a.acknowledged_at is null"
HISTORY = "(a.resolved_at is not null or a.acknowledged_at is not null)"


class AlertRepository(BaseRepository):
    def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        return [dict(r) for r in self.session.execute(text(sql), params or {}).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any] | None = None) -> Row | None:
        r = self.session.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None

    # ---------------------------------------------------------------- sources that have no service of their own
    def branches(self) -> dict[str, uuid.UUID]:
        return {r["name"]: r["id"] for r in self._all("select id, name from public.branches")}

    def task_rows(self, today: date) -> list[Row]:
        """Open tasks that are overdue, due today, or due in 1..7 days. One row per task and condition."""
        return self._all(
            """select t.id as record_id, t.title, t.due_date, t.branch_id, coalesce(b.name, 'All Branches') as branch_name,
                      coalesce(a.full_name, 'Unassigned') as assignee,
                      case when t.due_date < cast(:t as date) then 'task_overdue'
                           when t.due_date = cast(:t as date) then 'task_due_today'
                           else 'task_due_7' end as kind
                 from public.tasks t left join public.branches b on b.id = t.branch_id
                 left join public.profiles a on a.user_id = t.assignee_user_id
                where t.status <> 'Done' and t.due_date is not null and t.due_date <= cast(:t as date) + 7""",
            {"t": today},
        )

    def supplier_rows(self) -> list[Row]:
        return self._all(
            """select s.id as record_id, s.name, v.outstanding
                 from public.suppliers s join public.v_supplier_outstanding v on v.supplier_id = s.id
                where s.is_active and v.outstanding > 0"""
        )

    # ---------------------------------------------------------------- the alerts table
    def lock(self, key: int) -> None:
        self.session.execute(text("select pg_advisory_xact_lock(:k)"), {"k": key})

    def open_rows(self) -> list[Row]:
        return self._all("select * from public.alerts where resolved_at is null")

    def insert(self, v: Row) -> None:
        self.session.execute(
            text(
                """insert into public.alerts (alert_key, kind, module, severity, title, detail, record_id, branch_id,
                                              branch_name, due_date, href)
                   values (:alert_key, :kind, :module, :severity, :title, :detail, :record_id, :branch_id,
                           :branch_name, :due_date, :href)
                   on conflict (alert_key) where resolved_at is null do nothing"""
            ),
            v,
        )

    def refresh(self, id_: uuid.UUID, v: Row) -> None:
        self.session.execute(
            text(
                """update public.alerts set severity = :severity, title = :title, detail = :detail, branch_id = :branch_id,
                          branch_name = :branch_name, due_date = :due_date, href = :href, last_seen_at = now()
                    where id = :id"""
            ),
            {**v, "id": id_},
        )

    def resolve(self, ids: list[uuid.UUID]) -> None:
        if ids:
            self.session.execute(
                text(
                    "update public.alerts set resolved_at = now() where id = any(:ids) and resolved_at is null"
                ),
                {"ids": ids},
            )

    def get(self, id_: uuid.UUID, for_update: bool = False) -> Row | None:
        return self._one(
            SELECT + " where a.id = :i" + (" for update of a" if for_update else ""), {"i": id_}
        )

    def mark_read(self, id_: uuid.UUID) -> None:
        self.session.execute(
            text(
                """update public.alerts set read_at = now(), read_by = auth.uid()
                    where id = :i and read_at is null and resolved_at is null"""
            ),
            {"i": id_},
        )

    def acknowledge(self, id_: uuid.UUID) -> None:
        self.session.execute(
            text(
                """update public.alerts set read_at = coalesce(read_at, now()), read_by = coalesce(read_by, auth.uid()),
                          acknowledged_at = now(), acknowledged_by = auth.uid()
                    where id = :i and acknowledged_at is null and resolved_at is null"""
            ),
            {"i": id_},
        )

    def read_all(self) -> int:
        res: Any = self.session.execute(
            text(
                """update public.alerts set read_at = now(), read_by = auth.uid()
                    where read_at is null and resolved_at is null and acknowledged_at is null"""
            )
        )
        return int(res.rowcount)

    def counts(self) -> Row:
        r = self._one(
            f"""select count(*) filter (where {ACTIVE}) as total_active,
  count(*) filter (where {ACTIVE} and a.severity = 'critical') as critical,
  count(*) filter (where {ACTIVE} and a.severity = 'warning') as warning,
  count(*) filter (where {ACTIVE} and a.severity = 'info') as info,
  count(*) filter (where {ACTIVE} and a.read_at is null) as unread,
  count(*) filter (where a.resolved_at is null and a.acknowledged_at is not null) as acknowledged
from public.alerts a"""
        )
        assert r is not None
        return r

    def by_module(self) -> dict[str, int]:
        rows = self._all(
            f"select a.module, count(*) as n from public.alerts a where {ACTIVE} group by a.module"
        )
        return {r["module"]: int(r["n"]) for r in rows}

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
    ) -> tuple[list[Row], int]:
        where = [ACTIVE if scope == "active" else HISTORY]
        p: dict[str, Any] = {}
        if q:
            where.append(
                "(a.title ilike :q or a.detail ilike :q or coalesce(a.branch_name, '') ilike :q)"
            )
            p["q"] = f"%{q}%"
        if kind:
            where.append("a.kind = :kind")
            p["kind"] = kind
        if severity:
            where.append("a.severity = :sev")
            p["sev"] = severity
        if branch_id:
            where.append("a.branch_id = :b")
            p["b"] = branch_id
        if module:
            where.append("a.module = :m")
            p["m"] = module
        if status == "unread":
            where.append("a.read_at is null and a.resolved_at is null")
        elif status == "read":
            where.append(
                "a.read_at is not null and a.acknowledged_at is null and a.resolved_at is null"
            )
        elif status == "acknowledged":
            where.append("a.acknowledged_at is not null and a.resolved_at is null")
        elif status == "resolved":
            where.append("a.resolved_at is not null")
        w = " and ".join(where)
        total = self._one(f"select count(*) as n from public.alerts a where {w}", p)
        if scope == "active":
            order = f"{SEVERITY_ORDER}, a.due_date asc nulls last, a.first_seen_at desc, a.id"
        else:
            order = "coalesce(a.resolved_at, a.acknowledged_at) desc, a.id"
        rows = self._all(
            f"{SELECT} where {w} order by {order} limit :lim offset :off",
            {**p, "lim": page_size, "off": (page - 1) * page_size},
        )
        return rows, int(total["n"]) if total else 0

    def facets(self) -> list[Row]:
        return self._all("select distinct kind, module from public.alerts order by module, kind")
