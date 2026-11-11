import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.finance import AuditEntry, Strict

TaskStatus = Literal["To Do", "In Progress", "Done"]
Timing = Literal["completed", "no_due_date", "overdue", "due_today", "upcoming"]
_MIN, _MAX = date(2000, 1, 1), date(2100, 12, 31)


def _blank(v: str | None) -> str | None:
    return v if v else None


class TaskIn(Strict):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    branch_id: uuid.UUID | None = None  # null = All Branches (Owner only)
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None  # null = Unassigned (the approved default)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("description", "notes")
    @classmethod
    def _b(cls, v: str | None) -> str | None:
        return _blank(v)

    @field_validator("due_date")
    @classmethod
    def _d(cls, v: date | None) -> date | None:
        if v is not None and not (_MIN <= v <= _MAX):
            raise ValueError("Enter a realistic date (2000 to 2100)")
        return v


class TaskUpdate(TaskIn):
    reason: str | None = Field(default=None, max_length=500)


class StatusIn(Strict):
    status: TaskStatus
    note: str | None = Field(default=None, max_length=500)


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    branch_id: uuid.UUID | None
    branch_name: str  # "All Branches" when branch_id is null
    assignee_id: uuid.UUID | None
    assignee_name: str  # "Unassigned" when assignee_id is null
    due_date: date | None
    status: TaskStatus
    timing: Timing
    days_to_due: int | None
    notes: str | None
    created_at: datetime
    created_by_name: str | None
    updated_at: datetime
    updated_by_name: str | None
    completed_at: datetime | None
    completed_by_name: str | None


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int


class TaskDetail(BaseModel):
    task: TaskOut
    history: list[AuditEntry]


class TaskSummary(BaseModel):
    total: int
    to_do: int
    in_progress: int
    done: int
    overdue: int
    due_today: int
    due_7: int  # not Done, due today .. today + 7 days (includes today)


class Assignee(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    branch_name: str | None
