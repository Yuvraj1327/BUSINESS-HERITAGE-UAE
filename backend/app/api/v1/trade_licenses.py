import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.hr import (
    ArchiveIn,
    LicenseDetail,
    LicenseIn,
    LicensePage,
    LicenseSummary,
    LicenseUpdate,
    RenewalOut,
    RenewIn,
)
from app.services.license_service import LicenseService

router = APIRouter(prefix="/trade-licenses", tags=["trade-licenses"])
Read = Annotated[object, Depends(require_permission(Module.TRADE_LICENSES, Action.READ))]
Create = Annotated[object, Depends(require_permission(Module.TRADE_LICENSES, Action.CREATE))]
Update = Annotated[object, Depends(require_permission(Module.TRADE_LICENSES, Action.UPDATE))]


@router.get(
    "/summary", response_model=LicenseSummary, summary="Licence summary cards and renewal fees due"
)
def summary(session: DbSession, _p: Read) -> LicenseSummary:
    return LicenseService(session).summary()


@router.get(
    "", response_model=LicensePage, summary="Trade licences (search, filter, sort, paginate)"
)
def list_licenses(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    branch_id: uuid.UUID | None = None,
    status_: Annotated[
        Literal["expired", "urgent", "upcoming", "normal"] | None, Query(alias="status")
    ] = None,
    include_archived: bool = False,
    sort: Literal["expiry", "branch", "number", "fee"] = "expiry",
    desc: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> LicensePage:
    return LicenseService(session).search(
        q, branch_id, status_, include_archived, sort, desc, page, page_size
    )


@router.post(
    "", response_model=LicenseDetail, status_code=status.HTTP_201_CREATED, summary="Add a licence"
)
def create_license(body: LicenseIn, session: DbSession, _p: Create) -> LicenseDetail:
    return LicenseService(session).create(body)


@router.get(
    "/{license_id}", response_model=LicenseDetail, summary="Licence with renewals and history"
)
def get_license(license_id: uuid.UUID, session: DbSession, _p: Read) -> LicenseDetail:
    return LicenseService(session).detail(license_id)


@router.put("/{license_id}", response_model=LicenseDetail, summary="Update a licence")
def update_license(
    license_id: uuid.UUID, body: LicenseUpdate, session: DbSession, _p: Update
) -> LicenseDetail:
    return LicenseService(session).update(license_id, body)


@router.post("/{license_id}/renew", response_model=LicenseDetail, summary="Mark renewed (+1 year)")
def renew_license(
    license_id: uuid.UUID, body: RenewIn, session: DbSession, _p: Update
) -> LicenseDetail:
    return LicenseService(session).renew(license_id, body)


@router.get("/{license_id}/renewals", response_model=list[RenewalOut], summary="Renewal history")
def renewals(license_id: uuid.UUID, session: DbSession, _p: Read) -> list[RenewalOut]:
    return LicenseService(session).renewals(license_id)


@router.post(
    "/{license_id}/archive", status_code=status.HTTP_204_NO_CONTENT, summary="Archive a licence"
)
def archive_license(
    license_id: uuid.UUID, body: ArchiveIn, session: DbSession, _p: Update
) -> Response:
    LicenseService(session).archive(license_id, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
