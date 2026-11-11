"""First-login password change: the gate (password_change_required) and POST /auth/change-password."""

import json
import uuid

import httpx
import pytest
from pydantic import ValidationError

from app.core.exceptions import ForbiddenError
from app.core.security import TokenClaims
from app.schemas.auth import ChangePasswordRequest
from app.services.auth_service import AuthService, PasswordChangeRequiredError
from app.services.user_provisioning_service import (
    ProvisioningNotConfiguredError,
    change_own_password,
)
from tests.conftest import make_settings

UID = uuid.uuid4()
NEW = "An0therStrongPass"


class P:  # minimal profile
    def __init__(self, must: bool, active: bool = True) -> None:
        self.user_id, self.must_change_password, self.is_active = UID, must, active


class Repo:
    def __init__(self, profile: P) -> None:
        self.profile, self.cleared = profile, False

    def get(self, _id: uuid.UUID) -> P:
        return self.profile

    def complete_password_change(self) -> None:
        self.cleared = True


def claims() -> TokenClaims:
    return TokenClaims(
        user_id=UID, email=None, session_id=None, issued_at=None, expires_at=0, aal=None
    )


def test_pending_password_change_blocks_business_routes_but_not_profile_lookup() -> None:
    svc = AuthService(Repo(P(must=True)))  # type: ignore[arg-type]
    with pytest.raises(PasswordChangeRequiredError) as exc:
        svc.require_ready_profile(claims())
    assert isinstance(exc.value, ForbiddenError) and exc.value.code == "password_change_required"
    assert svc.require_active_profile(claims()).must_change_password is True


def test_no_pending_change_passes_the_gate() -> None:
    assert AuthService(Repo(P(must=False))).require_ready_profile(claims())  # type: ignore[arg-type]


def test_change_password_updates_auth_then_clears_flag() -> None:
    seen: list[tuple[str, str, dict]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path, json.loads(req.content)))
        return httpx.Response(200, json={})

    repo = Repo(P(must=True))
    settings = make_settings(supabase_url="https://x.supabase.co", supabase_service_role_key="k")
    change_own_password(repo, settings, UID, NEW, httpx.MockTransport(handler))  # type: ignore[arg-type]
    assert seen == [("PUT", f"/auth/v1/admin/users/{UID}", {"password": NEW})]
    assert repo.cleared


def test_flag_is_not_cleared_when_auth_rejects_the_password() -> None:
    from app.core.exceptions import AppError

    repo = Repo(P(must=True))
    settings = make_settings(supabase_url="https://x.supabase.co", supabase_service_role_key="k")
    transport = httpx.MockTransport(lambda _r: httpx.Response(500, json={}))
    with pytest.raises(AppError):
        change_own_password(repo, settings, UID, NEW, transport)  # type: ignore[arg-type]
    assert not repo.cleared


def test_unconfigured_server_refuses() -> None:
    with pytest.raises(ProvisioningNotConfiguredError):
        change_own_password(Repo(P(True)), make_settings(), UID, NEW)  # type: ignore[arg-type]


def test_request_validation() -> None:
    assert ChangePasswordRequest(new_password=NEW, confirm_password=NEW)  # type: ignore[arg-type]
    for bad in ("weak", "alllowercase1234"):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(new_password=bad, confirm_password=bad)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ChangePasswordRequest(new_password=NEW, confirm_password=NEW + "!")  # type: ignore[arg-type]
