import uuid

from sqlalchemy import text

from app.repositories.base import BaseRepository

_BRANCH = "select id, name, sort_order, is_active from public.branches"


class BranchRepository(BaseRepository):
    """Queries only. The caller's BranchScope adds the branch restriction; RLS enforces it again."""

    def list(self, only_branch: uuid.UUID | None) -> list[dict[str, object]]:
        sql = _BRANCH + (" where id = :b" if only_branch else "") + " order by sort_order, name"
        rows = (
            self.session.execute(text(sql), {"b": only_branch} if only_branch else {})
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def get(self, branch_id: uuid.UUID) -> dict[str, object] | None:
        row = (
            self.session.execute(text(_BRANCH + " where id = :b"), {"b": branch_id})
            .mappings()
            .first()
        )
        return None if row is None else dict(row)


__all__ = ["BranchRepository"]
