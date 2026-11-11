import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from app.repositories.base import BaseRepository

Row = dict[str, Any]

TASK_SELECT = """
select t.id, t.title, t.description, t.branch_id, coalesce(b.name, 'All Branches') as branch_name,
       t.assignee_user_id as assignee_id, coalesce(a.full_name, 'Unassigned') as assignee_name,
       t.due_date, t.status, t.notes, t.created_at, cr.full_name as created_by_name,
       t.updated_at, up.full_name as updated_by_name, t.completed_at, co.full_name as completed_by_name
  from public.tasks t
  left join public.branches b on b.id = t.branch_id
  left join public.profiles a on a.user_id = t.assignee_user_id
  left join public.profiles cr on cr.user_id = t.created_by
  left join public.profiles up on up.user_id = t.updated_by
  left join public.profiles co on co.user_id = t.completed_by"""

SORTS = {
    "due": "t.due_date",
    "created": "t.created_at",
    "title": "lower(t.title)",
    "status": "t.status",
}


class TaskRepository(BaseRepository):
    def _all(self, sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        return [dict(r) for r in self.session.execute(text(sql), params or {}).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any] | None = None) -> Row | None:
        r = self.session.execute(text(sql), params or {}).mappings().first()
        return dict(r) if r else None

    def set_reason(self, reason: str | None) -> None:
        self.session.execute(
            text("select set_config('app.audit_reason', :r, true)"), {"r": reason or ""}
        )

    def branch(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            "select id, name, is_active from public.branches where id = :i", {"i": id_}
        )

    def assignee(self, id_: uuid.UUID) -> Row | None:
        return self._one(
            "select user_id as id, full_name, is_active from public.profiles where user_id = :i",
            {"i": id_},
        )

    def assignees(self) -> list[Row]:
        return self._all(
            """select p.user_id as id, p.full_name as name, p.role, b.name as branch_name
                 from public.profiles p left join public.branches b on b.id = p.branch_id
                where p.is_active order by p.role, lower(p.full_name)"""
        )

    def history(self, id_: uuid.UUID, limit: int = 100) -> list[Row]:
        return self._all(
            """select a.id, a.occurred_at, p.full_name as actor_name, a.action, a.table_name, a.record_id, a.reason,
                      a.old_values, a.new_values
                 from public.audit_log a left join public.profiles p on p.user_id = a.actor_user_id
                where a.table_name = 'tasks' and a.record_id = :r order by a.id desc limit :n""",
            {"r": str(id_), "n": limit},
        )

    def get(self, id_: uuid.UUID, for_update: bool = False) -> Row | None:
        sql = TASK_SELECT + " where t.id = :i" + (" for update of t" if for_update else "")
        return self._one(sql, {"i": id_})

    def search(
        self,
        today: date,
        q: str | None,
        branch_id: uuid.UUID | None,
        all_branches: bool,
        status: str | None,
        assignee_id: uuid.UUID | None,
        unassigned: bool,
        due_from: date | None,
        due_to: date | None,
        view: str | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Row], int]:
        where = ["1 = 1"]
        p: dict[str, Any] = {"t": today}
        if q:
            where.append("(t.title ilike :q or coalesce(t.description, '') ilike :q)")
            p["q"] = f"%{q}%"
        if branch_id:
            where.append("t.branch_id = :b")
            p["b"] = branch_id
        if all_branches:
            where.append("t.branch_id is null")
        if status:
            where.append("t.status = :st")
            p["st"] = status
        if assignee_id:
            where.append("t.assignee_user_id = :a")
            p["a"] = assignee_id
        if unassigned:
            where.append("t.assignee_user_id is null")
        if due_from:
            where.append("t.due_date >= :df")
            p["df"] = due_from
        if due_to:
            where.append("t.due_date <= :dt")
            p["dt"] = due_to
        if view == "overdue":
            where.append("t.status <> 'Done' and t.due_date < cast(:t as date)")
        elif view == "today":
            where.append("t.status <> 'Done' and t.due_date = cast(:t as date)")
        elif view == "week":
            where.append(
                "t.status <> 'Done' and t.due_date between cast(:t as date) and cast(:t as date) + 7"
            )
        elif view == "upcoming":
            where.append("t.status <> 'Done' and t.due_date > cast(:t as date)")
        elif view == "open":
            where.append("t.status <> 'Done'")
        elif view == "completed":
            where.append("t.status = 'Done'")
        w = " and ".join(where)
        total = self._one(f"select count(*) as n from public.tasks t where {w}", p)
        order = SORTS[sort] + (" desc" if desc else " asc") + " nulls last, t.created_at desc, t.id"
        rows = self._all(
            f"{TASK_SELECT} where {w} order by {order} limit :lim offset :off",
            {**p, "lim": page_size, "off": (page - 1) * page_size},
        )
        return rows, int(total["n"]) if total else 0

    def summary(self, today: date) -> Row:
        r = self._one(
            """select count(*) as total,
  count(*) filter (where status = 'To Do') as to_do,
  count(*) filter (where status = 'In Progress') as in_progress,
  count(*) filter (where status = 'Done') as done,
  count(*) filter (where status <> 'Done' and due_date < cast(:t as date)) as overdue,
  count(*) filter (where status <> 'Done' and due_date = cast(:t as date)) as due_today,
  count(*) filter (where status <> 'Done' and due_date between cast(:t as date) and cast(:t as date) + 7) as due_7
from public.tasks""",
            {"t": today},
        )
        assert r is not None
        return r

    def insert(self, v: Row) -> uuid.UUID:
        return self.session.execute(
            text(
                """insert into public.tasks (title, description, branch_id, assignee_user_id, due_date, notes, status)
                   values (:title, :description, :branch_id, :assignee_id, :due_date, :notes, 'To Do') returning id"""
            ),
            v,
        ).scalar_one()

    def update(self, id_: uuid.UUID, v: Row) -> None:
        self.session.execute(
            text(
                """update public.tasks set title = :title, description = :description, branch_id = :branch_id,
                          assignee_user_id = :assignee_id, due_date = :due_date, notes = :notes where id = :id"""
            ),
            {**v, "id": id_},
        )

    def set_status(self, id_: uuid.UUID, status: str) -> None:
        self.session.execute(
            text("update public.tasks set status = :s where id = :id"), {"s": status, "id": id_}
        )
