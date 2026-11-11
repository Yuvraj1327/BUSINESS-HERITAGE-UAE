import json
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

    def branch_exists_active(self, branch_id: uuid.UUID) -> bool:
        row = self.session.execute(
            text("select is_active from public.branches where id = :id"), {"id": branch_id}
        ).first()
        return row is not None and bool(row[0])

    def add_branch_user(self, user_id: uuid.UUID, full_name: str, branch_id: uuid.UUID) -> Profile:
        """Insert a Branch User profile as the signed-in Owner (RLS policy profiles_insert_owner applies;
        the role is fixed here, never taken from a request). Commits."""
        profile = Profile(
            user_id=user_id,
            full_name=full_name,
            role="branch",
            branch_id=branch_id,
            is_active=True,
            must_change_password=True,  # the Owner chose the initial password; the user must replace it
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def complete_password_change(self) -> None:
        """Clear the caller's own must-change flag (SECURITY DEFINER function; touches only auth.uid()'s row)."""
        self.session.execute(text("select app.complete_password_change()"))
        self.session.commit()

    def update_own_profile(
        self, full_name: str, phone: str | None, avatar_path: str | None
    ) -> None:
        """Change the caller's own name / phone / photo (SECURITY DEFINER function; only auth.uid()'s row, and
        never role, branch or active status)."""
        self.session.execute(
            text("select app.update_own_profile(:n, :p, :a)"),
            {"n": full_name, "p": phone, "a": avatar_path},
        )
        self.session.commit()
        self.session.expire_all()

    def get_preferences(self, user_id: uuid.UUID) -> dict[str, object]:
        row = self.session.execute(
            text("select preferences from public.user_preferences where user_id = :u"),
            {"u": user_id},
        ).first()
        return dict(row[0]) if row is not None and isinstance(row[0], dict) else {}

    def save_preferences(self, user_id: uuid.UUID, preferences: dict[str, object]) -> None:
        """Upsert the caller's own row (RLS: user_preferences_*_own)."""
        self.session.execute(
            text(
                "insert into public.user_preferences (user_id, preferences) values (:u, cast(:p as jsonb)) "
                "on conflict (user_id) do update set preferences = excluded.preferences, updated_at = now()"
            ),
            {"u": user_id, "p": json.dumps(preferences)},
        )
        self.session.commit()
