import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.finance import (
    MarkPaidIn,
    SupplierDueIn,
    SupplierEntryOut,
    SupplierEntryPage,
    SupplierIn,
    SupplierOut,
    SupplierPage,
    SupplierPaymentIn,
    SupplierSummary,
    SupplierUpdate,
    VoidIn,
)
from app.services.supplier_service import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])
Read = Annotated[object, Depends(require_permission(Module.SUPPLIERS, Action.READ))]
Create = Annotated[object, Depends(require_permission(Module.SUPPLIERS, Action.CREATE))]
Update = Annotated[object, Depends(require_permission(Module.SUPPLIERS, Action.UPDATE))]


@router.get("/summary", response_model=SupplierSummary, summary="Supplier summary cards")
def summary(session: DbSession, _p: Read) -> SupplierSummary:
    return SupplierService(session).summary()


@router.get("", response_model=SupplierPage, summary="Suppliers (search, filter, sort, paginate)")
def list_suppliers(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[Literal["all", "active", "inactive"], Query(alias="status")] = "all",
    outstanding_only: bool = False,
    sort: Literal["name", "outstanding", "paid", "created"] = "name",
    desc: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SupplierPage:
    return SupplierService(session).list(q, status_, outstanding_only, sort, desc, page, page_size)


@router.post(
    "", response_model=SupplierOut, status_code=status.HTTP_201_CREATED, summary="Add a supplier"
)
def create_supplier(body: SupplierIn, session: DbSession, _p: Create) -> SupplierOut:
    return SupplierService(session).create(body)


# Declared before "/{supplier_id}" routes so "entries" is never parsed as an id.
@router.post(
    "/entries/{entry_id}/void",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Void a supplier due/payment",
)
def void_entry(entry_id: uuid.UUID, body: VoidIn, session: DbSession, _p: Update) -> Response:
    SupplierService(session).void_entry(entry_id, body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{supplier_id}", response_model=SupplierOut, summary="Supplier with outstanding breakdown"
)
def get_supplier(supplier_id: uuid.UUID, session: DbSession, _p: Read) -> SupplierOut:
    return SupplierService(session).get(supplier_id)


@router.put("/{supplier_id}", response_model=SupplierOut, summary="Update supplier details")
def update_supplier(
    supplier_id: uuid.UUID, body: SupplierUpdate, session: DbSession, _p: Update
) -> SupplierOut:
    return SupplierService(session).update(supplier_id, body)


@router.get(
    "/{supplier_id}/entries",
    response_model=SupplierEntryPage,
    summary="Supplier dues and payment history",
)
def list_entries(
    supplier_id: uuid.UUID,
    session: DbSession,
    _p: Read,
    kind: Literal["due", "payment"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SupplierEntryPage:
    return SupplierService(session).entries(supplier_id, kind, date_from, date_to, page, page_size)


@router.post(
    "/{supplier_id}/payments",
    response_model=SupplierEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a payment",
)
def pay(
    supplier_id: uuid.UUID, body: SupplierPaymentIn, session: DbSession, _p: Create
) -> SupplierEntryOut:
    return SupplierService(session).pay(supplier_id, body)


@router.post(
    "/{supplier_id}/mark-paid",
    response_model=SupplierEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Pay the full outstanding amount",
)
def mark_paid(
    supplier_id: uuid.UUID, body: MarkPaidIn, session: DbSession, _p: Create
) -> SupplierEntryOut:
    return SupplierService(session).mark_paid(supplier_id, body)


@router.post(
    "/{supplier_id}/dues",
    response_model=SupplierEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new due",
)
def record_due(
    supplier_id: uuid.UUID, body: SupplierDueIn, session: DbSession, _p: Create
) -> SupplierEntryOut:
    return SupplierService(session).record_due(supplier_id, body)
