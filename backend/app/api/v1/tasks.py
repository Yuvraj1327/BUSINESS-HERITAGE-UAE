import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.authz import require_permission
from app.api.deps import DbSession
from app.core.permissions import Action, Module
from app.schemas.tasks import (
    Assignee,
    StatusIn,
    TaskDetail,
    TaskIn,
    TaskPage,
    TaskSummary,
    TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])
Read = Annotated[object, Depends(require_permission(Module.TASKS, Action.READ))]
Create = Annotated[object, Depends(require_permission(Module.TASKS, Action.CREATE))]
Update = Annotated[object, Depends(require_permission(Module.TASKS, Action.UPDATE))]

View = Literal["overdue", "today", "week", "upcoming", "open", "completed"]


def _list(
    session: DbSession,
    view: View | None,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    all_branches: bool = False,
    status_: str | None = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
    due_from: date | None = None,
    due_to: date | None = None,
    sort: str = "due",
    desc: bool = False,
    page: int = 1,
    page_size: int = 25,
) -> TaskPage:
    return TaskService(session).search(
        q, branch_id, all_branches, status_, assignee_id, unassigned, due_from, due_to,
        view, sort, desc, page, page_size,
    )  # fmt: skip


# Static paths are declared before "/{task_id}" so they are never parsed as ids.
@router.get("/summary", response_model=TaskSummary, summary="Task dashboard cards")
def summary(session: DbSession, _p: Read) -> TaskSummary:
    return TaskService(session).summary()


@router.get(
    "/assignees", response_model=list[Assignee], summary="Active users a task can be assigned to"
)
def assignees(session: DbSession, _p: Read) -> list[Assignee]:
    return TaskService(session).assignees()


@router.get(
    "/overdue", response_model=TaskPage, summary="Overdue tasks (due date passed, not Done)"
)
def overdue(
    session: DbSession,
    _p: Read,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TaskPage:
    return _list(session, "overdue", page=page, page_size=page_size)


@router.get(
    "/upcoming", response_model=TaskPage, summary="Open tasks due today .. 7 days, soonest first"
)
def upcoming(
    session: DbSession,
    _p: Read,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TaskPage:
    return _list(session, "week", page=page, page_size=page_size)


@router.get("", response_model=TaskPage, summary="Tasks (search, filter, sort, paginate)")
def list_tasks(
    session: DbSession,
    _p: Read,
    q: Annotated[str | None, Query(max_length=100)] = None,
    branch_id: uuid.UUID | None = None,
    all_branches: bool = False,
    status_: Annotated[
        Literal["To Do", "In Progress", "Done"] | None, Query(alias="status")
    ] = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
    due_from: date | None = None,
    due_to: date | None = None,
    view: View | None = None,
    sort: Literal["due", "created", "title", "status"] = "due",
    desc: bool = False,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TaskPage:
    return _list(
        session, view, q, branch_id, all_branches, status_, assignee_id, unassigned,
        due_from, due_to, sort, desc, page, page_size,
    )  # fmt: skip


@router.post(
    "", response_model=TaskDetail, status_code=status.HTTP_201_CREATED, summary="Create a task"
)
def create_task(body: TaskIn, session: DbSession, _p: Create) -> TaskDetail:
    return TaskService(session).create(body)


@router.get("/{task_id}", response_model=TaskDetail, summary="Task with change history")
def get_task(task_id: uuid.UUID, session: DbSession, _p: Read) -> TaskDetail:
    return TaskService(session).detail(task_id)


@router.get("/{task_id}/history", response_model=TaskDetail, summary="Task history")
def task_history(task_id: uuid.UUID, session: DbSession, _p: Read) -> TaskDetail:
    return TaskService(session).detail(task_id)


@router.put(
    "/{task_id}", response_model=TaskDetail, summary="Update a task (details, branch, assignee)"
)
def update_task(task_id: uuid.UUID, body: TaskUpdate, session: DbSession, _p: Update) -> TaskDetail:
    return TaskService(session).update(task_id, body)


@router.post("/{task_id}/status", response_model=TaskDetail, summary="Change a task's status")
def set_status(task_id: uuid.UUID, body: StatusIn, session: DbSession, _p: Update) -> TaskDetail:
    return TaskService(session).set_status(task_id, body)


@router.post("/{task_id}/complete", response_model=TaskDetail, summary="Mark a task as completed")
def complete(task_id: uuid.UUID, session: DbSession, _p: Update) -> TaskDetail:
    return TaskService(session).set_status(task_id, StatusIn(status="Done"))
