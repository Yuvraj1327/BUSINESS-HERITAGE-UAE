import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.core.passwords import validate_new_password


class BranchOut(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool


class UserOut(BaseModel):
    """Profile data for Owner user management (read-only for now). No email, no tokens, no secrets."""

    user_id: uuid.UUID
    full_name: str
    role: str
    branch_id: uuid.UUID | None
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    """Owner creates a Branch User with an initial password. There is no role field on purpose: the role is
    always 'branch'. Passwords are SecretStr: never echoed in errors, logs or responses."""

    # hide_input_in_errors: a ValidationError must never carry the submitted passwords (it would reach logs).
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=1, max_length=150)
    branch_id: uuid.UUID
    password: SecretStr
    confirm_password: SecretStr

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("full_name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be blank")
        return v

    @model_validator(mode="after")
    def _password_rules(self) -> "UserCreate":
        pw = self.password.get_secret_value()
        if pw != self.confirm_password.get_secret_value():
            raise ValueError("Passwords do not match")
        validate_new_password(pw, self.email)
        return self
