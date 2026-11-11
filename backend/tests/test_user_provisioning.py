"""Owner-driven Branch User provisioning: authorization, validation, compensation. No database needed
(the repository is a stub; the Supabase Auth admin API is an httpx MockTransport)."""

import json
import uuid

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError
from app.core.permissions import Principal, Role
from app.schemas.rbac import UserCreate
from app.services.user_admin_policy import InvalidUserChange, UserAdminDenied
from app.services.user_provisioning_service import (
    ProvisioningNotConfiguredError,
    UserProvisioningService,
)
from tests.conftest import make_settings

BRANCH = uuid.uuid4()
NEW_ID = uuid.uuid4()


def principal(role: Role, branch: uuid.UUID | None = None) -> Principal:
    return Principal(user_id=uuid.uuid4(), role=role, branch_id=branch, full_name="Actor")


class StubSession:
    rolled_back = False

    def rollback(self) -> None:
        self.rolled_back = True


class StubProfiles:
    def __init__(self, *, branch_ok: bool = True, fail: Exception | None = None) -> None:
        self.session = StubSession()
        self.branch_ok = branch_ok
        self.fail = fail
        self.added: list[tuple[uuid.UUID, str, uuid.UUID]] = []

    def branch_exists_active(self, _id: uuid.UUID) -> bool:
        return self.branch_ok

    def add_branch_user(self, user_id: uuid.UUID, name: str, branch_id: uuid.UUID) -> str:
        if self.fail:
            raise self.fail
        self.added.append((user_id, name, branch_id))
        return "profile"


class AuthStub:
    def __init__(
        self, create_status: int = 200, error: dict | None = None, confirm: bool = True
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[dict] = []
        self.create_status = create_status
        self.error = error or {"msg": "exists"}
        self.confirm = confirm

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.method, req.url.path))
        if req.url.path.endswith("/admin/users") and req.method == "POST":
            body = json.loads(req.content)
            assert body == {
                "email": "new@example.com",
                "password": PASSWORD,
                "email_confirm": self.confirm,
            }
            self.bodies.append(body)
            if self.create_status != 200:
                return httpx.Response(self.create_status, json=self.error)
            return httpx.Response(200, json={"id": str(NEW_ID)})
        return httpx.Response(200, json={})


def service(profiles: StubProfiles, stub: AuthStub, configured: bool = True):
    extra = (
        {
            "supabase_url": "https://x.supabase.co",
            "supabase_service_role_key": "k",
        }
        if configured
        else {}
    )
    return UserProvisioningService(
        profiles,  # type: ignore[arg-type]
        make_settings(**extra),
        httpx.MockTransport(stub),
    )


PASSWORD = "Str0ngPassw0rd!"
DATA = UserCreate(
    email="New@Example.com",
    full_name="  Satwa Manager ",
    branch_id=BRANCH,
    password=PASSWORD,
    confirm_password=PASSWORD,
)


def test_owner_creates_branch_user_with_password_and_no_email() -> None:
    profiles, stub = StubProfiles(), AuthStub()
    result = service(profiles, stub).create_branch_user(principal(Role.OWNER), DATA)
    assert result == "profile"
    assert profiles.added == [(NEW_ID, "Satwa Manager", BRANCH)]
    assert stub.calls == [
        ("POST", "/auth/v1/admin/users")
    ]  # no invitation / recovery email, no extra calls


def test_branch_user_cannot_create_accounts_and_nothing_is_called() -> None:
    profiles, stub = StubProfiles(), AuthStub()
    with pytest.raises(UserAdminDenied):
        service(profiles, stub).create_branch_user(principal(Role.BRANCH_USER, BRANCH), DATA)
    assert stub.calls == [] and profiles.added == []


def test_unconfigured_server_refuses_clearly() -> None:
    with pytest.raises(ProvisioningNotConfiguredError):
        service(StubProfiles(), AuthStub(), configured=False).create_branch_user(
            principal(Role.OWNER), DATA
        )


def test_unknown_or_inactive_branch_is_rejected_before_creating_an_auth_user() -> None:
    stub = AuthStub()
    with pytest.raises(InvalidUserChange):
        service(StubProfiles(branch_ok=False), stub).create_branch_user(principal(Role.OWNER), DATA)
    assert stub.calls == []


def test_duplicate_profile_removes_the_new_auth_user_again() -> None:
    profiles = StubProfiles(fail=IntegrityError("x", {}, Exception("dup")))
    stub = AuthStub()
    with pytest.raises(ConflictError):
        service(profiles, stub).create_branch_user(principal(Role.OWNER), DATA)
    assert profiles.session.rolled_back
    assert ("DELETE", f"/auth/v1/admin/users/{NEW_ID}") in stub.calls


def test_existing_auth_email_is_a_conflict_and_creates_no_profile() -> None:
    profiles = StubProfiles()
    with pytest.raises(ConflictError):
        service(profiles, AuthStub(create_status=422)).create_branch_user(
            principal(Role.OWNER), DATA
        )
    assert profiles.added == []


def test_email_confirmation_follows_the_owners_provisioning_decision() -> None:
    stub = AuthStub(confirm=False)
    svc = UserProvisioningService(
        StubProfiles(),  # type: ignore[arg-type]
        make_settings(
            supabase_url="https://x.supabase.co",
            supabase_service_role_key="k",
            provision_email_confirmed=False,
        ),
        httpx.MockTransport(stub),
    )
    svc.create_branch_user(principal(Role.OWNER), DATA)
    assert stub.bodies[0]["email_confirm"] is False


def test_weak_password_from_the_auth_provider_is_a_field_error_not_a_conflict() -> None:
    from app.core.exceptions import UnprocessableError

    stub = AuthStub(create_status=422, error={"error_code": "weak_password", "msg": "weak"})
    with pytest.raises(UnprocessableError):
        service(StubProfiles(), stub).create_branch_user(principal(Role.OWNER), DATA)


def test_non_integrity_profile_failure_also_removes_the_auth_user() -> None:
    profiles = StubProfiles(fail=RuntimeError("db down"))
    stub = AuthStub()
    with pytest.raises(RuntimeError):
        service(profiles, stub).create_branch_user(principal(Role.OWNER), DATA)
    assert ("DELETE", f"/auth/v1/admin/users/{NEW_ID}") in stub.calls


def test_request_schema_has_no_role_field_and_validates_input() -> None:
    ok = {"full_name": "X", "branch_id": BRANCH, "password": PASSWORD, "confirm_password": PASSWORD}
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.co", role="owner", **ok)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", **ok)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        UserCreate(email="a@b.co", **{**ok, "full_name": "   "})  # type: ignore[arg-type]
    assert DATA.email == "new@example.com"


@pytest.mark.parametrize(
    "pw",
    [
        "short1A",
        "alllowercase123",
        "ALLUPPERCASE123",
        "NoDigitsHereAtAll",
        "x" * 80 + "Aa1",
        "newuser-Abc12345",
    ],
)
def test_weak_passwords_are_rejected(pw: str) -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="newuser@example.com",
            full_name="X",
            branch_id=BRANCH,
            password=pw,
            confirm_password=pw,
        )


def test_password_confirmation_must_match_and_is_never_echoed() -> None:
    with pytest.raises(ValidationError) as exc:
        UserCreate(
            email="a@b.co",
            full_name="X",
            branch_id=BRANCH,
            password=PASSWORD,
            confirm_password=PASSWORD + "x",
        )
    assert PASSWORD not in str(exc.value) and "do not match" in str(exc.value)
    assert PASSWORD not in repr(DATA)  # SecretStr: safe in logs / tracebacks
