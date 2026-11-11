import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.hr import (
    ArchiveIn,
    EmployeeDetail,
    EmployeeIn,
    EmployeePage,
    EmployeeSummary,
    EmployeeUpdate,
    LeaveSummary,
    LeaveUpdateIn,
    ReturnIn,
    StatusChangeIn,
)
from app.services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["employees"])
Read = Annotated[object, Depends(require_permission(Module.EMPLOYEES, Action.READ))]
Create = Annotated[object, Depends(require_permission(Module.EMPLOYEES, Action.CREATE))]
Update = Annotated[object, Depends(require_permission(Module.EMPLOYEES, Action.UPDATE))]


# Static paths are declared before "/{employee_id}" so they are never parsed as ids.
@router.get(
    "/summary", response_model=EmployeeSummary, summary="Employee summary cards and payroll total"
)
def summary(session: DbSession, _p: Read) -> EmployeeSummary:
    return EmployeeService(session).summary()


@router.get(
    "/leave/summary", response_model=LeaveSummary, summary="Leave summary and six-month watch list"
)
def leave_summary(session: DbSession, _p: Read) -> LeaveSummary:
    return EmployeeService(session).leave_summary()


@router.get("", response_model=EmployeePage, summary="Employees (search, filter, sort, paginate)")
def list_employees(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    branch_id: uuid.UUID | None = None,
    status_: Annotated[
        Literal["Active", "On Leave", "Visa Cancelled"] | None, Query(alias="status")
    ] = None,
    include_archived: bool = False,
    sort: Literal["name", "branch", "role", "salary", "status", "created"] = "name",
    desc: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> EmployeePage:
    return EmployeeService(session).list(
        q, branch_id, status_, include_archived, sort, desc, page, page_size
    )


@router.post(
    "",
    response_model=EmployeeDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Add an employee",
)
def create_employee(body: EmployeeIn, session: DbSession, _p: Create) -> EmployeeDetail:
    return EmployeeService(session).create(body)


@router.get("/{employee_id}", response_model=EmployeeDetail, summary="Employee with change history")
def get_employee(employee_id: uuid.UUID, session: DbSession, _p: Read) -> EmployeeDetail:
    return EmployeeService(session).detail(employee_id)


@router.put("/{employee_id}", response_model=EmployeeDetail, summary="Update an employee")
def update_employee(
    employee_id: uuid.UUID, body: EmployeeUpdate, session: DbSession, _p: Update
) -> EmployeeDetail:
    return EmployeeService(session).update(employee_id, body)


@router.post(
    "/{employee_id}/status", response_model=EmployeeDetail, summary="Change employment status"
)
def change_status(
    employee_id: uuid.UUID, body: StatusChangeIn, session: DbSession, _p: Update
) -> EmployeeDetail:
    return EmployeeService(session).change_status(employee_id, body)


@router.post("/{employee_id}/return", response_model=EmployeeDetail, summary="Return to work")
def return_to_work(
    employee_id: uuid.UUID, body: ReturnIn, session: DbSession, _p: Update
) -> EmployeeDetail:
    return EmployeeService(session).record_return(employee_id, body)


@router.patch(
    "/{employee_id}/leave", response_model=EmployeeDetail, summary="Correct the leave start date"
)
def update_leave(
    employee_id: uuid.UUID, body: LeaveUpdateIn, session: DbSession, _p: Update
) -> EmployeeDetail:
    return EmployeeService(session).update_leave(employee_id, body)


@router.post(
    "/{employee_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive an employee (no hard delete)",
)
def archive_employee(
    employee_id: uuid.UUID, body: ArchiveIn, session: DbSession, _p: Update
) -> Response:
    EmployeeService(session).archive(employee_id, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
