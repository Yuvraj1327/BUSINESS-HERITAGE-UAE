from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.authz import BranchScope, get_branch_scope
from app.api.deps import DbSession
from app.api.v1.orders import SortKey, order_filters
from app.core.permissions import Action, Module
from app.repositories.order_repository import OrderFilter
from app.schemas.orders import OrderPage
from app.services.order_insights_service import OperationView, OrderInsightsService

router = APIRouter(prefix="/order-operations", tags=["order-operations"])
Read = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDERS, Action.READ))]
Filters = Annotated[OrderFilter, Depends(order_filters)]


@router.get("/counts", response_model=dict[str, int], summary="Size of every operations view")
def counts(
    session: DbSession,
    scope: Read,
    f: Filters,
    day: Annotated[date | None, Query(alias="date")] = None,
) -> dict[str, int]:
    return OrderInsightsService(session).operation_counts(scope, day, f)


@router.get("/{view}", response_model=OrderPage, summary="Pickup / delivery operations view")
def operations(
    view: OperationView, session: DbSession, scope: Read, f: Filters,
    day: Annotated[date | None, Query(alias="date")] = None, sort: SortKey | None = None,
    desc: bool | None = None, page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OrderPage:  # fmt: skip
    return OrderInsightsService(session).operations(
        scope, view, day, f, sort, desc, page, page_size
    )
