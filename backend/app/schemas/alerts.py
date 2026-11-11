import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Severity = Literal["critical", "warning", "info"]
AlertStatus = Literal["unread", "read", "acknowledged", "resolved"]


class AlertOut(BaseModel):
    id: uuid.UUID
    alert_key: str
    kind: str
    type_label: str
    module: str
    title: str
    detail: str
    record_id: str | None
    branch_id: uuid.UUID | None
    branch_name: str | None
    alert_date: date  # the Dubai date the condition was first seen
    due_date: date | None
    severity: Severity
    status: AlertStatus
    href: str
    first_seen_at: datetime
    last_seen_at: datetime
    read_at: datetime | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class AlertPage(BaseModel):
    items: list[AlertOut]
    total: int
    page: int
    page_size: int


class AlertSummary(BaseModel):
    total_active: int
    critical: int
    warning: int
    info: int
    unread: int
    acknowledged: int  # still true, acknowledged by the Owner (in history, not active)
    recent: list[AlertOut]  # the most important active alerts first
    by_module: dict[str, int]


class UnreadCount(BaseModel):
    unread: int
    total_active: int


class AlertFacets(BaseModel):
    kinds: list[tuple[str, str]]
    modules: list[tuple[str, str]]
