import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from app.core.passwords import validate_new_password


class AuthMeResponse(BaseModel):
    """What the verified access token proves. No profile data, no raw token, no secrets."""

    user_id: uuid.UUID
    email: str | None
    session_id: str | None
    expires_at: int
    authenticated: Literal[True] = True


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    full_name: str
    role: Literal["owner", "branch"]
    branch_id: uuid.UUID | None
    branch_name: str | None
    is_active: bool
    # True until the user replaces the Owner-issued initial password. The API refuses everything else meanwhile.
    must_change_password: bool = False
    # Display hints for the UI, derived from the central matrix. The API re-checks every request.
    permissions: dict[str, dict[str, Any]]


class ChangePasswordRequest(BaseModel):
    """First-login password change. Passwords are SecretStr: never echoed, logged or serialised."""

    # hide_input_in_errors: a ValidationError must never carry the submitted passwords (it would reach logs).
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    new_password: SecretStr
    confirm_password: SecretStr

    @model_validator(mode="after")
    def _check(self) -> "ChangePasswordRequest":
        if self.new_password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("Passwords do not match")
        validate_new_password(self.new_password.get_secret_value())
        return self
