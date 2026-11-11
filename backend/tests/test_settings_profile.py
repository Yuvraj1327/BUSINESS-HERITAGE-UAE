"""Self-service Settings: own profile edit and preferences (service + schema level; no database needed)."""

import uuid

import pytest
from pydantic import ValidationError

from app.core.exceptions import UnprocessableError
from app.core.security import TokenClaims
from app.schemas.settings import Preferences, ProfileUpdate
from app.services.auth_service import AuthService, PasswordChangeRequiredError

UID = uuid.uuid4()
GOOD_PATH = f"{UID}/avatar-{uuid.uuid4()}.png"


class P:
    def __init__(self, must: bool = False) -> None:
        self.user_id, self.full_name, self.role = UID, "Old Name", "branch"
        self.branch_id, self.is_active, self.must_change_password = uuid.uuid4(), True, must
        self.phone, self.avatar_path = "+971 50 123 4567", None


class Repo:
    def __init__(self, profile: P) -> None:
        self.profile = profile
        self.saved: list[tuple[str, str | None, str | None]] = []
        self.prefs: dict[str, object] = {}

    def get(self, _id: uuid.UUID) -> P:
        return self.profile

    def branch_name(self, _b: object) -> str:
        return "SATWA"

    def update_own_profile(self, name: str, phone: str | None, avatar: str | None) -> None:
        self.saved.append((name, phone, avatar))
        self.profile.full_name, self.profile.phone, self.profile.avatar_path = name, phone, avatar

    def get_preferences(self, _id: uuid.UUID) -> dict[str, object]:
        return self.prefs

    def save_preferences(self, _id: uuid.UUID, prefs: dict[str, object]) -> None:
        self.prefs = prefs


def claims(uid: uuid.UUID = UID) -> TokenClaims:
    return TokenClaims(
        user_id=uid, email=None, session_id=None, issued_at=None, expires_at=0, aal=None
    )


def svc(profile: P | None = None) -> tuple[AuthService, Repo]:
    repo = Repo(profile or P())
    return AuthService(repo), repo  # type: ignore[arg-type]


def test_edit_changes_only_sent_fields() -> None:
    s, repo = svc()
    out = s.update_own_profile(claims(), ProfileUpdate(full_name="  New Name "))
    assert repo.saved == [("New Name", "+971 50 123 4567", None)]
    assert out.full_name == "New Name" and out.role == "branch" and out.branch_name == "SATWA"


def test_phone_can_be_cleared_and_photo_set() -> None:
    s, repo = svc()
    s.update_own_profile(claims(), ProfileUpdate(phone="", avatar_path=GOOD_PATH))
    assert repo.saved == [("Old Name", None, GOOD_PATH)]


def test_other_users_photo_is_refused() -> None:
    s, repo = svc()
    other = f"{uuid.uuid4()}/avatar-{uuid.uuid4()}.png"
    with pytest.raises(UnprocessableError):
        s.update_own_profile(claims(), ProfileUpdate(avatar_path=other))
    assert repo.saved == []


@pytest.mark.parametrize("field", ["role", "branch_id", "is_active", "user_id"])
def test_role_branch_and_status_are_not_accepted(field: str) -> None:
    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate({field: "x"})


@pytest.mark.parametrize("phone", ["abc", "12", "+971<script>"])
def test_bad_phone_rejected(phone: str) -> None:
    with pytest.raises(ValidationError):
        ProfileUpdate(phone=phone)


@pytest.mark.parametrize(
    "path", ["../x.png", f"{UID}/avatar.png", f"{UID}/avatar-{uuid.uuid4()}.svg"]
)
def test_bad_avatar_path_rejected(path: str) -> None:
    with pytest.raises(ValidationError):
        ProfileUpdate(avatar_path=path)


def test_blank_name_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileUpdate(full_name="   ")


def test_pending_password_change_blocks_edits() -> None:
    s, _ = svc(P(must=True))
    with pytest.raises(PasswordChangeRequiredError):
        s.update_own_profile(claims(), ProfileUpdate(full_name="X"))
    with pytest.raises(PasswordChangeRequiredError):
        s.save_preferences(claims(), Preferences())


def test_preferences_round_trip_and_defaults() -> None:
    s, repo = svc()
    assert s.profile_response(claims()).preferences == Preferences()
    out = s.save_preferences(claims(), Preferences(theme="dark", date_format="yyyy-mm-dd"))
    assert repo.prefs["theme"] == "dark" and out.preferences.date_format == "yyyy-mm-dd"


def test_damaged_stored_preferences_fall_back_to_defaults() -> None:
    s, repo = svc()
    repo.prefs = {"theme": "neon"}
    assert s.profile_response(claims()).preferences == Preferences()


@pytest.mark.parametrize(
    "bad", [{"timezone": "Mars/Base"}, {"theme": "x"}, {"language": "fr"}, {"extra": 1}]
)
def test_invalid_preferences_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Preferences.model_validate(bad)
