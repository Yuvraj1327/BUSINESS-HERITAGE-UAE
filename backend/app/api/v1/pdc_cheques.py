import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.rentals import (
    BounceIn,
    ChequeDetail,
    ChequePage,
    ChequeSummary,
    ChequeUpdate,
    ClearIn,
    ReplaceIn,
)
from app.services.cheque_service import ChequeService

router = APIRouter(prefix="/pdc-cheques", tags=["pdc-cheques"])
Read = Annotated[object, Depends(require_permission(Module.RENTALS_CHEQUES, Action.READ))]
Update = Annotated[object, Depends(require_permission(Module.RENTALS_CHEQUES, Action.UPDATE))]


@router.get("/summary", response_model=ChequeSummary, summary="PDC summary cards and next cheque")
def summary(session: DbSession, _p: Read) -> ChequeSummary:
    return ChequeService(session).summary()


@router.get("", response_model=ChequePage, summary="PDC cheques (search, filter, sort, paginate)")
def list_cheques(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    branch_id: uuid.UUID | None = None,
    bank: Literal["ENBD", "ADCB"] | None = None,
    status_: Annotated[
        Literal["Pending", "Cleared", "Bounced"] | None, Query(alias="status")
    ] = None,
    view: Literal["overdue", "upcoming", "bounced_open"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    agreement_id: uuid.UUID | None = None,
    sort: Literal["date", "number", "amount", "branch", "landlord"] = "date",
    desc: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ChequePage:
    return ChequeService(session).search(
        q,
        branch_id,
        bank,
        status_,
        view,
        date_from,
        date_to,
        agreement_id,
        sort,
        desc,
        page,
        page_size,
    )


@router.get(
    "/{cheque_id}", response_model=ChequeDetail, summary="Cheque with agreement and history"
)
def get_cheque(cheque_id: uuid.UUID, session: DbSession, _p: Read) -> ChequeDetail:
    return ChequeService(session).detail(cheque_id)


@router.post("/{cheque_id}/clear", response_model=ChequeDetail, summary="Mark a cheque cleared")
def clear(cheque_id: uuid.UUID, body: ClearIn, session: DbSession, _p: Update) -> ChequeDetail:
    return ChequeService(session).clear(cheque_id, body)


@router.post("/{cheque_id}/bounce", response_model=ChequeDetail, summary="Mark a cheque bounced")
def bounce(cheque_id: uuid.UUID, body: BounceIn, session: DbSession, _p: Update) -> ChequeDetail:
    return ChequeService(session).bounce(cheque_id, body)


@router.post(
    "/{cheque_id}/replace", response_model=ChequeDetail, summary="Replace a bounced cheque"
)
def replace(cheque_id: uuid.UUID, body: ReplaceIn, session: DbSession, _p: Update) -> ChequeDetail:
    return ChequeService(session).replace(cheque_id, body)


@router.patch("/{cheque_id}", response_model=ChequeDetail, summary="Edit a pending cheque")
def update_cheque(
    cheque_id: uuid.UUID, body: ChequeUpdate, session: DbSession, _p: Update
) -> ChequeDetail:
    return ChequeService(session).update(cheque_id, body)
