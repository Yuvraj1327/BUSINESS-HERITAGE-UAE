import uuid
from typing import Any, Literal

from pydantic import BaseModel


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
    # Display hints for the UI, derived from the central matrix. The API re-checks every request.
    permissions: dict[str, dict[str, Any]]
