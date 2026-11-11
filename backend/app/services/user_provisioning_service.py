"""Owner-driven account provisioning: Auth user (with the Owner's initial password) + profile.

Order: authorize -> validate branch -> create Auth user (Supabase Admin API) -> insert profile as the Owner
(one DB transaction, RLS applies) . If the profile insert fails the Auth user is deleted again, so there is never
an Auth user without a profile created by this flow. No invitation email is involved: the Branch User can sign
in at once and must change the initial password on first login (profiles.must_change_password).

Passwords exist only in memory for the duration of the call and are forwarded to Supabase Auth over HTTPS. They are
never stored in profiles, never logged, never put in audit history, never returned. The service-role key stays
in the backend. Only Branch Users can be created here; Owners are provisioned by an operator
(docs/authentication/OWNER_ACCOUNT_SETUP.md).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    ConflictError,
    ServiceUnavailableError,
    UnprocessableError,
)
from app.core.permissions import Principal, Role
from app.models.profile import Profile
from app.repositories.profile_repository import ProfileRepository
from app.schemas.rbac import UserCreate
from app.services.user_admin_policy import (
    InvalidUserChange,
    UserAdminAction,
    authorize_user_change,
)

logger = logging.getLogger(__name__)


class ProvisioningNotConfiguredError(ServiceUnavailableError):
    code = "provisioning_not_configured"


class AuthProviderError(AppError):
    status_code, code = 502, "auth_provider_error"


class SupabaseAuthAdmin:
    """Minimal Supabase Auth admin client. Never logs request bodies, responses or the key."""

    def __init__(
        self, base_url: str, service_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base = base_url.rstrip("/") + "/auth/v1"
        self.http = httpx.Client(
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=15,
            transport=transport,
        )

    def _call(self, method: str, url: str, what: str, **kw: Any) -> dict[str, Any]:
        try:
            resp = self.http.request(method, url, **kw)
        except httpx.HTTPError:
            raise AuthProviderError(f"Could not reach the sign-in service ({what}).") from None
        if resp.status_code >= 400:
            self._raise_for_error(resp, what)
        return resp.json() if resp.content else {}

    @staticmethod
    def _raise_for_error(resp: httpx.Response, what: str) -> None:
        try:
            payload = resp.json()
            error_code = str(payload.get("error_code") or payload.get("code") or "")
            msg = str(payload.get("msg") or payload.get("message") or "")
        except ValueError:
            error_code = msg = ""
        if resp.status_code == 409 or error_code in {"email_exists", "user_already_exists"}:
            raise ConflictError("An account with this email already exists.")
        if resp.status_code == 422 and (error_code == "weak_password" or "password" in msg.lower()):
            raise UnprocessableError(
                "The password was not accepted by the sign-in service.",
                fields={"password": ["Choose a stronger password"]},
            )
        if resp.status_code == 422 and ("already" in msg.lower() or "exist" in msg.lower()):
            raise ConflictError("An account with this email already exists.")
        raise AuthProviderError(f"The sign-in service refused the request ({what}).")

    def create_user(self, email: str, password: str, *, email_confirmed: bool) -> uuid.UUID:
        body = self._call(
            "POST",
            f"{self.base}/admin/users",
            "creating the user",
            json={"email": email, "password": password, "email_confirm": email_confirmed},
        )
        return uuid.UUID(str(body["id"]))

    def update_password(self, user_id: uuid.UUID, password: str) -> None:
        self._call(
            "PUT",
            f"{self.base}/admin/users/{user_id}",
            "changing the password",
            json={"password": password},
        )

    def delete_user(self, user_id: uuid.UUID) -> None:
        self._call("DELETE", f"{self.base}/admin/users/{user_id}", "removing the user")


def build_auth_admin(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> SupabaseAuthAdmin:
    if settings.supabase_url is None or settings.supabase_service_role_key is None:
        raise ProvisioningNotConfiguredError(
            "This action is not configured on the server (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required)."
        )
    return SupabaseAuthAdmin(
        str(settings.supabase_url), settings.supabase_service_role_key.get_secret_value(), transport
    )


class UserProvisioningService:
    def __init__(
        self,
        profiles: ProfileRepository,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.profiles = profiles
        self.settings = settings
        self.transport = transport

    def create_branch_user(self, actor: Principal, data: UserCreate) -> Profile:
        authorize_user_change(
            actor,
            UserAdminAction.CREATE_BRANCH_USER,
            new_role=Role.BRANCH_USER,
            new_branch_id=data.branch_id,
        )
        admin = build_auth_admin(self.settings, self.transport)
        if not self.profiles.branch_exists_active(data.branch_id):
            raise InvalidUserChange("Choose an existing, active branch.")
        user_id = admin.create_user(
            data.email,
            data.password.get_secret_value(),
            email_confirmed=self.settings.provision_email_confirmed,
        )
        try:
            return self.profiles.add_branch_user(user_id, data.full_name, data.branch_id)
        except IntegrityError:
            self.profiles.session.rollback()
            self._compensate(admin, user_id)
            raise ConflictError("This user already has a profile.") from None
        except BaseException:
            self.profiles.session.rollback()
            self._compensate(admin, user_id)
            raise

    @staticmethod
    def _compensate(admin: SupabaseAuthAdmin, user_id: uuid.UUID) -> None:
        try:
            admin.delete_user(user_id)
        except AppError:
            logger.error("could not remove Auth user %s after a failed profile insert", user_id)


def change_own_password(
    profiles: ProfileRepository,
    settings: Settings,
    user_id: uuid.UUID,
    new_password: str,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Set the caller's new password in Supabase Auth, then clear their must-change flag.

    If clearing the flag fails the password is already changed and the call can simply be repeated."""
    build_auth_admin(settings, transport).update_password(user_id, new_password)
    profiles.complete_password_change()
