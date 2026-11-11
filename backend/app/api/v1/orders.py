import logging
import uuid
from datetime import date
from typing import Annotated, Literal, get_args

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.authz import BranchScope, get_branch_scope
from app.api.deps import DbSession
from app.core import orders as rules
from app.core.permissions import Action, Module
from app.repositories.order_repository import SORTS, OrderFilter
from app.schemas.analytics import ReportCatalogItem, ReportOut
from app.schemas.orders import (
    Balance,
    CancelIn,
    CategoryOut,
    HistoryItem,
    OrderDashboard,
    OrderDetail,
    OrderIn,
    OrderPage,
    OrderStatus,
    OrderUpdate,
    PaymentIn,
    PaymentOut,
    PaymentStatus,
    PaymentSummary,
    RefundIn,
    ServiceType,
    StatusIn,
)
from app.services import export_service as exp
from app.services.order_insights_service import OrderInsightsService
from app.services.order_service import OrderService
from app.utils.time import dubai_today

logger = logging.getLogger("app.audit")
router = APIRouter(prefix="/orders", tags=["orders"])

Read = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDERS, Action.READ))]
Create = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDERS, Action.CREATE))]
Update = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDERS, Action.UPDATE))]
Manage = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDERS, Action.MANAGE))]
Export = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDERS, Action.EXPORT))]
PayRead = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDER_PAYMENTS, Action.READ))]
PayCreate = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDER_PAYMENTS, Action.CREATE))]
PayManage = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDER_PAYMENTS, Action.MANAGE))]

SortKey = Literal[
    "order_no",
    "order_date",
    "pickup",
    "delivery",
    "customer",
    "status",
    "amount",
    "outstanding",
    "created",
]
assert set(SORTS) == set(get_args(SortKey))  # keep the API choices and the SQL map in step


def order_filters(
    branch_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: OrderStatus | None = None,
    payment_status: PaymentStatus | None = None,
    category_id: uuid.UUID | None = None,
    service_type: ServiceType | None = None,
    area: Annotated[str | None, Query(max_length=100)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    pickup_date: date | None = None,
    delivery_date: date | None = None,
) -> OrderFilter:
    return OrderFilter(
        branch_id=branch_id, q=(q or "").strip() or None, status=status, payment_status=payment_status,
        category_id=category_id, service_type=service_type, area=(area or "").strip() or None,
        order_from=date_from, order_to=date_to,
        pickup_bounds=rules.day_bounds(pickup_date) if pickup_date else None,
        delivery_bounds=rules.day_bounds(delivery_date) if delivery_date else None,
    )  # fmt: skip


Filters = Annotated[OrderFilter, Depends(order_filters)]


# ---- static paths first (never parsed as an order id) ---------------------------------------------------------
@router.get("/service-categories", response_model=list[CategoryOut], summary="Service categories")
def categories(session: DbSession, _s: Read) -> list[CategoryOut]:
    return OrderService(session).categories()


@router.get("/dashboard", response_model=OrderDashboard, summary="Order Management dashboard")
def dashboard(
    session: DbSession,
    scope: Read,
    f: Filters,
    day: Annotated[date | None, Query(alias="date")] = None,
) -> OrderDashboard:
    return OrderInsightsService(session).dashboard(scope, day, f)


@router.get("/payments/summary", response_model=PaymentSummary, summary="Order payments by method")
def payments_summary(
    session: DbSession, scope: PayRead, date_from: date | None = None, date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
) -> PaymentSummary:  # fmt: skip
    today = dubai_today()
    end = date_to or today
    data = OrderService(session).payment_summary(
        scope, branch_id, date_from or end.replace(day=1), end
    )
    return PaymentSummary(**data)


@router.get("/reports/catalog", response_model=list[ReportCatalogItem], summary="Order reports")
def report_catalog(session: DbSession, _s: Read) -> list[ReportCatalogItem]:
    return OrderInsightsService(session).catalog()


def _report_args(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    end = date_to or dubai_today()
    return (date_from or end.replace(day=1)), end


@router.get("/reports/{key}", response_model=ReportOut, summary="One order report")
def report(
    key: str, session: DbSession, scope: Read, f: Filters, date_from: date | None = None,
    date_to: date | None = None, period: Literal["day", "week"] = "day", sort: Annotated[str | None, Query(max_length=40)] = None,
    desc: bool = False, page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> ReportOut:  # fmt: skip
    d_from, d_to = _report_args(date_from, date_to)
    return OrderInsightsService(session).report(
        scope, key, d_from, d_to, period, f, sort, desc, page, page_size
    )


@router.get("/reports/{key}/export", summary="Export one order report as CSV or Excel")
def export(
    key: str, session: DbSession, scope: Export, f: Filters, format: Literal["csv", "xlsx"] = "csv",
    date_from: date | None = None, date_to: date | None = None, period: Literal["day", "week"] = "day",
) -> Response:  # fmt: skip
    d_from, d_to = _report_args(date_from, date_to)
    rep = OrderInsightsService(session).report(
        scope, key, d_from, d_to, period, f, None, False, 1, 25, export=True
    )
    logger.info(
        "order_export key=%s format=%s rows=%d user=%s branch=%s", key, format, rep.total,
        scope.principal.user_id, rep.filters.branch_id,
    )  # fmt: skip
    data = exp.to_csv(rep) if format == "csv" else exp.to_xlsx(rep)
    return Response(
        content=data, media_type=exp.CSV_TYPE if format == "csv" else exp.XLSX_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{exp.filename(rep, format)}"', "Cache-Control": "no-store"},
    )  # fmt: skip


# ---- orders ----------------------------------------------------------------------------------------------------
@router.post(
    "", response_model=OrderDetail, status_code=status.HTTP_201_CREATED, summary="Create an order"
)
def create_order(body: OrderIn, session: DbSession, scope: Create) -> OrderDetail:
    return OrderService(session).create(scope, body)


@router.get("", response_model=OrderPage, summary="Orders (filters, search, sort, pages)")
def list_orders(
    session: DbSession, scope: Read, f: Filters, sort: SortKey = "created", desc: bool = True,
    page: Annotated[int, Query(ge=1, le=100000)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OrderPage:  # fmt: skip
    return OrderService(session).list_orders(scope, f, sort, desc, page, page_size)


@router.get("/{order_id}", response_model=OrderDetail, summary="Order details")
def get_order(order_id: uuid.UUID, session: DbSession, scope: Read) -> OrderDetail:
    return OrderService(session).detail(scope, order_id)


@router.put("/{order_id}", response_model=OrderDetail, summary="Edit an open order")
def update_order(
    order_id: uuid.UUID, body: OrderUpdate, session: DbSession, scope: Update
) -> OrderDetail:
    return OrderService(session).update(scope, order_id, body)


@router.post(
    "/{order_id}/status", response_model=OrderDetail, summary="Move the order to its next status"
)
def set_status(
    order_id: uuid.UUID, body: StatusIn, session: DbSession, scope: Update
) -> OrderDetail:
    return OrderService(session).set_status(scope, order_id, body)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderDetail,
    summary="Cancel an order (reason and confirmation)",
)
def cancel_order(
    order_id: uuid.UUID, body: CancelIn, session: DbSession, scope: Manage
) -> OrderDetail:
    return OrderService(session).cancel(scope, order_id, body)


@router.get(
    "/{order_id}/status-history", response_model=list[HistoryItem], summary="Status history"
)
def status_history(order_id: uuid.UUID, session: DbSession, scope: Read) -> list[HistoryItem]:
    return OrderService(session).history(scope, order_id)


@router.get("/{order_id}/payments", response_model=list[PaymentOut], summary="Payment history")
def payments(order_id: uuid.UUID, session: DbSession, scope: PayRead) -> list[PaymentOut]:
    return OrderService(session).payments(scope, order_id)


@router.get("/{order_id}/balance", response_model=Balance, summary="Outstanding balance")
def balance(order_id: uuid.UUID, session: DbSession, scope: PayRead) -> Balance:
    return OrderService(session).balance(scope, order_id)


@router.post(
    "/{order_id}/payments",
    response_model=Balance,
    status_code=status.HTTP_201_CREATED,
    summary="Record a payment",
)
def add_payment(
    order_id: uuid.UUID, body: PaymentIn, session: DbSession, scope: PayCreate
) -> Balance:
    return OrderService(session).add_payment(scope, order_id, body)


@router.post(
    "/{order_id}/refund",
    status_code=status.HTTP_409_CONFLICT,
    summary="Refund (disabled until a workflow is approved)",
)
def refund(order_id: uuid.UUID, body: RefundIn, session: DbSession, scope: PayManage) -> None:
    OrderService(session).refund(scope, order_id, body)
