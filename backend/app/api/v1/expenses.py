import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.finance import (
    ExpenseCategoryOut,
    ExpenseCorrectionIn,
    ExpenseDetail,
    ExpenseIn,
    ExpenseOut,
    ExpensePage,
    SavingIn,
    VoidIn,
)
from app.services.expense_service import ExpenseService

router = APIRouter(prefix="/expenses", tags=["expenses"])
Read = Annotated[object, Depends(require_permission(Module.EXPENSES, Action.READ))]
Create = Annotated[object, Depends(require_permission(Module.EXPENSES, Action.CREATE))]
Update = Annotated[object, Depends(require_permission(Module.EXPENSES, Action.UPDATE))]


@router.get("/categories", response_model=list[ExpenseCategoryOut], summary="Expense categories")
def categories(session: DbSession, _p: Read) -> list[ExpenseCategoryOut]:
    return ExpenseService(session).categories()


@router.get("", response_model=ExpensePage, summary="Head office expenses (filters + pagination)")
def list_expenses(
    session: DbSession,
    _p: Read,
    date_from: date | None = None,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
    all_branches_only: bool = False,
    category_id: uuid.UUID | None = None,
    paid_from: Literal["Cash", "ENBD", "ADCB"] | None = None,
    is_saving: bool | None = None,
    include_voided: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ExpensePage:
    return ExpenseService(session).list(
        date_from,
        date_to,
        branch_id,
        all_branches_only,
        category_id,
        paid_from,
        is_saving,
        include_voided,
        page,
        page_size,
    )


@router.post(
    "",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a head office expense",
)
def create_expense(body: ExpenseIn, session: DbSession, _p: Create) -> ExpenseOut:
    return ExpenseService(session).create(body)


@router.get("/{expense_id}", response_model=ExpenseDetail, summary="Expense with its audit history")
def get_expense(expense_id: uuid.UUID, session: DbSession, _p: Read) -> ExpenseDetail:
    return ExpenseService(session).get(expense_id)


@router.put(
    "/{expense_id}",
    response_model=ExpenseOut,
    summary="Correct an expense (void + replace, reason required)",
)
def correct_expense(
    expense_id: uuid.UUID, body: ExpenseCorrectionIn, session: DbSession, _p: Update
) -> ExpenseOut:
    return ExpenseService(session).correct(expense_id, body)


@router.post(
    "/{expense_id}/void",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete = void with a reason",
)
def void_expense(expense_id: uuid.UUID, body: VoidIn, session: DbSession, _p: Update) -> Response:
    ExpenseService(session).void(expense_id, body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{expense_id}/saving",
    response_model=ExpenseOut,
    summary="Mark / unmark as saving (reason required)",
)
def set_saving(expense_id: uuid.UUID, body: SavingIn, session: DbSession, _p: Update) -> ExpenseOut:
    return ExpenseService(session).set_saving(expense_id, body.is_saving, body.reason)
