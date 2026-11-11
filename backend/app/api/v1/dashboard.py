from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.authz import BranchScope
from app.api.deps import DbSession
from app.api.scope_guards import require_all_branches
from app.core.permissions import Action, Module
from app.schemas.dashboard import OwnerDashboard
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/owner", response_model=OwnerDashboard, summary="Owner dashboard (day or month, all branches)"
)
def owner_dashboard(
    session: DbSession,
    _scope: Annotated[BranchScope, Depends(require_all_branches(Module.DASHBOARD, Action.READ))],
    mode: Literal["day", "month"] = "day",
    day: Annotated[date | None, Query(alias="date")] = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> OwnerDashboard:
    return DashboardService(session).owner_dashboard(mode, day, month)
