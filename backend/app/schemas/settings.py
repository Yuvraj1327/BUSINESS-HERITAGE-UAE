"""Self-service Settings: own profile fields and personal preferences.

Role, branch and active status are deliberately absent: they can never be changed through these models
(and the database refuses it as well). Mirrors frontend/src/schemas/settings.ts.
"""

import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 'Asia/Dubai' is the business timezone (reports, cut-offs, "today"). The others only change how timestamps are
# DISPLAYED to this user; business dates are always computed in Dubai (app.utils.time).
DISPLAY_TIMEZONES = (
    "Asia/Dubai",
    "device",
    "UTC",
    "Asia/Kolkata",
    "Asia/Karachi",
    "Asia/Manila",
    "Europe/London",
)
Theme = Literal["light", "dark", "system"]
Language = Literal["en"]
DateFormat = Literal["dd-mmm-yyyy", "dd/mm/yyyy", "mm/dd/yyyy", "yyyy-mm-dd"]

PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")
AVATAR_RE = re.compile(
    r"^(?P<uid>[0-9a-f-]{36})/avatar-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|png|webp)$"
)


class NotificationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical: bool = True
    warning: bool = True
    info: bool = True


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: Theme = "system"
    language: Language = "en"
    date_format: DateFormat = "dd-mmm-yyyy"
    timezone: str = "Asia/Dubai"
    notifications: NotificationPreferences = Field(default_factory=NotificationPreferences)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, v: str) -> str:
        if v not in DISPLAY_TIMEZONES:
            raise ValueError("Unsupported timezone")
        return v


class ProfileUpdate(BaseModel):
    """Only the fields a user may edit about themselves. Omitted fields keep their value; null clears phone/photo."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    avatar_path: str | None = Field(default=None, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Name must not be blank")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return None
        if not PHONE_RE.match(v):
            raise ValueError("Enter a valid phone number (digits, spaces, + ( ) - only)")
        return v

    @field_validator("avatar_path")
    @classmethod
    def _avatar(cls, v: str | None) -> str | None:
        if v is not None and not AVATAR_RE.match(v):
            raise ValueError("Invalid photo path")
        return v


def avatar_belongs_to(path: str, user_id: uuid.UUID) -> bool:
    m = AVATAR_RE.match(path)
    return m is not None and m.group("uid") == str(user_id)
