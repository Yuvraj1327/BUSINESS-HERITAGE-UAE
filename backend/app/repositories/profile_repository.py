import uuid
from dataclasses import dataclass

from sqlalchemy import select, text

from app.models.profile import Profile
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class ProfileWithBranch:
    profile: Profile
    branch_name: str | None


class ProfileRepository(BaseRepository):
    """Queries only. Runs inside a user-context session, so RLS decides what is visible."""

    def get(self, user_id: uuid.UUID) -> Profile | None:
        return self.session.get(Profile, user_id)

    def branch_name(self, branch_id: uuid.UUID | None) -> str | None:
        if branch_id is None:
            return None
        row = self.session.execute(
            text("select name from public.branches where id = :id"), {"id": branch_id}
        ).first()
        return None if row is None else str(row[0])

    def list_all(self) -> list[Profile]:
        """All profiles visible to the caller (RLS: only an owner sees more than their own row)."""
        return list(self.session.scalars(select(Profile).order_by(Profile.full_name)))
