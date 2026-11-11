from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.hr import AlertFeed
from app.services.compliance_service import ComplianceService

router = APIRouter(prefix="/compliance", tags=["compliance"])
Read = Annotated[object, Depends(require_permission(Module.VISAS_PASSPORTS, Action.READ))]


@router.get(
    "/alerts",
    response_model=AlertFeed,
    summary="Owner compliance alerts (one per record and condition)",
)
def alerts(session: DbSession, _p: Read) -> AlertFeed:
    return ComplianceService(session).alerts()
