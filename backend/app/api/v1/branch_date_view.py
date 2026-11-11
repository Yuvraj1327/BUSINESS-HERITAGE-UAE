import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.authz import BranchScope, get_branch_scope
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.dashboard import BranchDateView
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/branch-date-view", tags=["branch-date-view"])


@router.get("", response_model=BranchDateView, summary="Branch & date view")
def branch_date_view(
    session: DbSession,
    scope: Annotated[BranchScope, Depends(get_branch_scope(Module.DAILY_REPORTS, Action.READ))],
    date_from: date,
    date_to: date,
    branch_id: uuid.UUID | None = None,
) -> BranchDateView:
    """Owner: all branches or one. Branch user: own branch only (another id is a 403). Head-office data is owner-only."""
    return DashboardService(session).branch_date_view(scope, branch_id, date_from, date_to)
