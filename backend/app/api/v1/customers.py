import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.authz import BranchScope, get_branch_scope
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.orders import CustomerIn, CustomerOut, CustomerPage, CustomerUpdate, OrderPage
from app.services.order_service import OrderService

router = APIRouter(prefix="/customers", tags=["customers"])
Read = Annotated[BranchScope, Depends(get_branch_scope(Module.CUSTOMERS, Action.READ))]
Create = Annotated[BranchScope, Depends(get_branch_scope(Module.CUSTOMERS, Action.CREATE))]
Update = Annotated[BranchScope, Depends(get_branch_scope(Module.CUSTOMERS, Action.UPDATE))]
OrdersRead = Annotated[BranchScope, Depends(get_branch_scope(Module.ORDERS, Action.READ))]


@router.post(
    "", response_model=CustomerOut, status_code=status.HTTP_201_CREATED, summary="Create a customer"
)
def create_customer(body: CustomerIn, session: DbSession, scope: Create) -> CustomerOut:
    return OrderService(session).create_customer(scope, body)


@router.get("", response_model=CustomerPage, summary="Customers (search by name or mobile)")
def list_customers(
    session: DbSession,
    scope: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    branch_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CustomerPage:
    return OrderService(session).list_customers(scope, branch_id, q, page, page_size)


@router.get("/{customer_id}", response_model=CustomerOut, summary="One customer")
def get_customer(customer_id: uuid.UUID, session: DbSession, scope: Read) -> CustomerOut:
    return OrderService(session).get_customer(scope, customer_id)


@router.put(
    "/{customer_id}", response_model=CustomerOut, summary="Update contact and address details"
)
def update_customer(
    customer_id: uuid.UUID, body: CustomerUpdate, session: DbSession, scope: Update
) -> CustomerOut:
    return OrderService(session).update_customer(scope, customer_id, body)


@router.get(
    "/{customer_id}/orders", response_model=OrderPage, summary="The customer's order history"
)
def customer_orders(
    customer_id: uuid.UUID,
    session: DbSession,
    scope: OrdersRead,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OrderPage:
    return OrderService(session).customer_orders(scope, customer_id, page, page_size)
