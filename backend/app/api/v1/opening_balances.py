from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.finance import AuditEntry, OpeningBalancesIn, OpeningBalancesOut
from app.services.opening_service import OpeningBalanceService

router = APIRouter(prefix="/opening-balances", tags=["opening-balances"])
Read = Annotated[object, Depends(require_permission(Module.OPENING_BALANCES, Action.READ))]
Write = Annotated[object, Depends(require_permission(Module.OPENING_BALANCES, Action.UPDATE))]


@router.get("", response_model=OpeningBalancesOut, summary="Opening balances (owner only)")
def get_opening(session: DbSession, _p: Read) -> OpeningBalancesOut:
    return OpeningBalanceService(session).get()


@router.put("", response_model=OpeningBalancesOut, summary="Create or correct the opening balances")
def save_opening(body: OpeningBalancesIn, session: DbSession, _p: Write) -> OpeningBalancesOut:
    """First save creates the configuration; later saves are audited corrections that need a reason."""
    return OpeningBalanceService(session).save(body)


@router.get(
    "/history", response_model=list[AuditEntry], summary="Audit history of opening balances"
)
def opening_history(session: DbSession, _p: Read) -> list[AuditEntry]:
    return OpeningBalanceService(session).history()
