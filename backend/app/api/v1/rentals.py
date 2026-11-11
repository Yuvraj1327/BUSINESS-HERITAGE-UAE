import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.rentals import (
    AgreementDetail,
    AgreementIn,
    AgreementPage,
    AgreementUpdate,
    RenewalLink,
    RenewalPreview,
    RenewConfirmIn,
    RenewIn,
    RentalAlertFeed,
    RentalSummary,
    ScheduleOut,
    ScheduleParams,
    SchedulePreview,
)
from app.services.agreement_service import AgreementService
from app.services.rental_alert_service import RentalAlertService

router = APIRouter(prefix="/rentals", tags=["rentals"])
Read = Annotated[object, Depends(require_permission(Module.RENTALS_CHEQUES, Action.READ))]
Create = Annotated[object, Depends(require_permission(Module.RENTALS_CHEQUES, Action.CREATE))]
Update = Annotated[object, Depends(require_permission(Module.RENTALS_CHEQUES, Action.UPDATE))]

AgreementStatusQ = Literal["Active", "Expiring", "Expired", "Scheduled", "Renewed", "Terminated"]


@router.get("/summary", response_model=RentalSummary, summary="Rental and PDC summary cards")
def summary(session: DbSession, _p: Read) -> RentalSummary:
    return RentalAlertService(session).rental_summary()


@router.get("/alerts", response_model=RentalAlertFeed, summary="Rental and PDC alerts (Owner only)")
def alerts(session: DbSession, _p: Read) -> RentalAlertFeed:
    return RentalAlertService(session).alerts()


@router.post(
    "/schedule-preview",
    response_model=SchedulePreview,
    summary="Preview the cheque schedule before saving",
)
def schedule_preview(body: ScheduleParams, session: DbSession, _p: Read) -> SchedulePreview:
    return AgreementService(session).preview(body)


@router.get(
    "/upcoming-expiries",
    response_model=AgreementPage,
    summary="Agreements ending soonest (default 90 days)",
)
def upcoming_expiries(
    session: DbSession,
    _p: Read,
    days: Annotated[int, Query(ge=1, le=365)] = 90,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AgreementPage:
    return AgreementService(session).search(None, None, None, "end", False, page, page_size, days)


@router.get(
    "", response_model=AgreementPage, summary="Rental agreements (search, filter, sort, paginate)"
)
def list_agreements(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    branch_id: uuid.UUID | None = None,
    status_: Annotated[AgreementStatusQ | None, Query(alias="status")] = None,
    sort: Literal["end", "start", "branch", "landlord", "rent"] = "end",
    desc: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AgreementPage:
    return AgreementService(session).search(q, branch_id, status_, sort, desc, page, page_size)


@router.post(
    "",
    response_model=AgreementDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm a rental agreement and its cheque schedule",
)
def create_agreement(body: AgreementIn, session: DbSession, _p: Create) -> AgreementDetail:
    return AgreementService(session).create(body)


@router.get(
    "/{agreement_id}", response_model=AgreementDetail, summary="Agreement, schedule and history"
)
def get_agreement(agreement_id: uuid.UUID, session: DbSession, _p: Read) -> AgreementDetail:
    return AgreementService(session).detail(agreement_id)


@router.put("/{agreement_id}", response_model=AgreementDetail, summary="Update an active agreement")
def update_agreement(
    agreement_id: uuid.UUID, body: AgreementUpdate, session: DbSession, _p: Update
) -> AgreementDetail:
    return AgreementService(session).update(agreement_id, body)


@router.get(
    "/{agreement_id}/schedule", response_model=ScheduleOut, summary="Linked PDC cheque schedule"
)
def get_schedule(agreement_id: uuid.UUID, session: DbSession, _p: Read) -> ScheduleOut:
    return AgreementService(session).schedule(agreement_id)


@router.get(
    "/{agreement_id}/renewals", response_model=list[RenewalLink], summary="Renewal history chain"
)
def get_renewals(agreement_id: uuid.UUID, session: DbSession, _p: Read) -> list[RenewalLink]:
    return AgreementService(session).renewals(agreement_id)


@router.post(
    "/{agreement_id}/renewal-preview",
    response_model=RenewalPreview,
    summary="Old-vs-new summary and new schedule (nothing is saved)",
)
def renewal_preview(
    agreement_id: uuid.UUID, body: RenewIn, session: DbSession, _p: Read
) -> RenewalPreview:
    return AgreementService(session).renewal_preview(agreement_id, body)


@router.post(
    "/{agreement_id}/renew",
    response_model=AgreementDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm the renewal (Owner)",
)
def renew(
    agreement_id: uuid.UUID, body: RenewConfirmIn, session: DbSession, _p: Create
) -> AgreementDetail:
    return AgreementService(session).renew(agreement_id, body)
