import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.hr import (
    CompliancePage,
    ComplianceSummary,
    EmployeeDetail,
    ExpiryChange,
    ExpiryUpdateIn,
)
from app.services.compliance_service import ComplianceService

router = APIRouter(prefix="/visas-passports", tags=["visas-passports"])
Read = Annotated[object, Depends(require_permission(Module.VISAS_PASSPORTS, Action.READ))]
Update = Annotated[object, Depends(require_permission(Module.VISAS_PASSPORTS, Action.UPDATE))]
Bucket = Literal["expired", "urgent", "upcoming", "normal", "not_recorded", "cancelled"]


@router.get(
    "/summary", response_model=ComplianceSummary, summary="Visa and passport expiry summary"
)
def summary(session: DbSession, _p: Read) -> ComplianceSummary:
    return ComplianceService(session).summary()


def _list(kind: Literal["visa", "passport"]):  # type: ignore[no-untyped-def]
    def handler(
        session: DbSession,
        _p: Read,
        q: Annotated[str | None, Query(max_length=100)] = None,
        branch_id: uuid.UUID | None = None,
        bucket: Bucket | None = None,
        sort: Literal["expiry", "name", "branch"] = "expiry",
        desc: bool = False,
        page: Annotated[int, Query(ge=1, le=100000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> CompliancePage:
        return ComplianceService(session).search(
            kind, q, branch_id, bucket, sort, desc, page, page_size
        )

    return handler


router.add_api_route(
    "/visas", _list("visa"), methods=["GET"], response_model=CompliancePage, summary="Visa records"
)
router.add_api_route(
    "/passports",
    _list("passport"),
    methods=["GET"],
    response_model=CompliancePage,
    summary="Passport records",
)


@router.patch(
    "/employees/{employee_id}/visa-expiry",
    response_model=EmployeeDetail,
    summary="Update a visa expiry date",
)
def update_visa(
    employee_id: uuid.UUID, body: ExpiryUpdateIn, session: DbSession, _p: Update
) -> EmployeeDetail:
    return ComplianceService(session).update_expiry(employee_id, "visa", body)


@router.patch(
    "/employees/{employee_id}/passport-expiry",
    response_model=EmployeeDetail,
    summary="Update a passport expiry date",
)
def update_passport(
    employee_id: uuid.UUID, body: ExpiryUpdateIn, session: DbSession, _p: Update
) -> EmployeeDetail:
    return ComplianceService(session).update_expiry(employee_id, "passport", body)


@router.get(
    "/employees/{employee_id}/history",
    response_model=dict[str, list[ExpiryChange]],
    summary="Visa and passport expiry change history",
)
def history(employee_id: uuid.UUID, session: DbSession, _p: Read) -> dict[str, list[ExpiryChange]]:
    svc = ComplianceService(session)
    return {
        "visa": svc.history(employee_id, "visa"),
        "passport": svc.history(employee_id, "passport"),
    }
