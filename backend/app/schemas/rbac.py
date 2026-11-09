import uuid
from datetime import datetime

from pydantic import BaseModel


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
