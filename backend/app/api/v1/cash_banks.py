import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.finance import (
    AccountsReport,
    Balances,
    BranchCashReport,
    LedgerPage,
    PosSettlementIn,
    PosSettlementOut,
    TransferIn,
    TransferOut,
    VoidIn,
)
from app.services.cash_bank_service import CashBankService

router = APIRouter(prefix="/cash-banks", tags=["cash-banks"])
Read = Annotated[object, Depends(require_permission(Module.CASH_BANKS, Action.READ))]
Create = Annotated[object, Depends(require_permission(Module.CASH_BANKS, Action.CREATE))]
Update = Annotated[object, Depends(require_permission(Module.CASH_BANKS, Action.UPDATE))]


@router.get("/summary", response_model=Balances, summary="Current balances")
def summary(session: DbSession, _p: Read, as_of: date | None = None) -> Balances:
    return CashBankService(session).summary(as_of)


@router.get(
    "/accounts",
    response_model=AccountsReport,
    summary="Opening / incoming / outgoing / closing per account",
)
def accounts(
    session: DbSession, _p: Read, date_from: date | None = None, date_to: date | None = None
) -> AccountsReport:
    return CashBankService(session).accounts(date_from, date_to)


@router.get("/branches", response_model=BranchCashReport, summary="Branch-wise cash balances")
def branches(session: DbSession, _p: Read, as_of: date | None = None) -> BranchCashReport:
    return CashBankService(session).branches(as_of)


@router.get("/transactions", response_model=LedgerPage, summary="Cash and bank transaction history")
def transactions(
    session: DbSession,
    _p: Read,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Literal["Cash", "ENBD", "ADCB", "POS Pending"] | None = None,
    branch_id: uuid.UUID | None = None,
    txn_type: Annotated[str | None, Query(max_length=60)] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> LedgerPage:
    return CashBankService(session).transactions(
        date_from, date_to, account, branch_id, txn_type, page, page_size
    )


@router.get("/transfers", response_model=list[TransferOut], summary="Recent transfers")
def list_transfers(session: DbSession, _p: Read) -> list[TransferOut]:
    return CashBankService(session).transfers()


@router.post(
    "/transfers",
    response_model=TransferOut,
    status_code=status.HTTP_201_CREATED,
    summary="Transfer between accounts",
)
def create_transfer(body: TransferIn, session: DbSession, _p: Create) -> TransferOut:
    return CashBankService(session).create_transfer(body)


@router.post(
    "/transfers/{transfer_id}/void",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Void a transfer",
)
def void_transfer(transfer_id: uuid.UUID, body: VoidIn, session: DbSession, _p: Update) -> Response:
    CashBankService(session).void_transfer(transfer_id, body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/pos-settlements", response_model=list[PosSettlementOut], summary="Recent POS settlements"
)
def list_settlements(session: DbSession, _p: Read) -> list[PosSettlementOut]:
    return CashBankService(session).settlements()


@router.post(
    "/pos-settlements",
    response_model=PosSettlementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a POS settlement",
)
def create_settlement(body: PosSettlementIn, session: DbSession, _p: Create) -> PosSettlementOut:
    return CashBankService(session).create_settlement(body)


@router.post(
    "/pos-settlements/{settlement_id}/void",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Void a POS settlement",
)
def void_settlement(
    settlement_id: uuid.UUID, body: VoidIn, session: DbSession, _p: Update
) -> Response:
    CashBankService(session).void_settlement(settlement_id, body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
