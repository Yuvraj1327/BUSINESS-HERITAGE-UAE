"""Task Management (Step 11). Owner only: the approved matrix gives Branch Users no access to tasks (D11 unresolved)."""

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.authz import PermissionDeniedError
from app.core import tasks as rules
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.repositories.task_repository import TaskRepository
from app.schemas.tasks import (
    Assignee,
    StatusIn,
    TaskDetail,
    TaskIn,
    TaskOut,
    TaskPage,
    TaskSummary,
    TaskUpdate,
)
from app.services.base import BaseService
from app.services.finance_core import _message, sqlstate
from app.utils.time import dubai_today

logger = logging.getLogger(__name__)


def task_dict(row: dict[str, Any], today: date) -> dict[str, Any]:
    timing, days = rules.timing_of(row["status"], row["due_date"], today)
    return {**row, "timing": timing, "days_to_due": days}


class TaskService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.repo = TaskRepository(session)

    # ---- plumbing --------------------------------------------------------------------------------------------
    def run(self, fn: Any) -> Any:
        try:
            return fn()
        except DBAPIError as exc:
            self.session.rollback()
            state = sqlstate(exc)
            if state == "42501":
                raise PermissionDeniedError() from exc
            if state in ("23514", "23503"):
                raise UnprocessableError(_message(exc) or "The task breaks a rule") from exc
            logger.warning("unmapped database error %s", state)
            raise
        except Exception:
            self.session.rollback()
            raise

    def _out(self, row: dict[str, Any], today: date) -> TaskOut:
        return TaskOut(**task_dict(row, today))

    def _load(self, id_: uuid.UUID, for_update: bool = False) -> dict[str, Any]:
        row = self.repo.get(id_, for_update)
        if row is None:
            raise NotFoundError("Task not found")
        return row

    def _check_refs(self, branch_id: uuid.UUID | None, assignee_id: uuid.UUID | None) -> None:
        if branch_id is not None:
            b = self.repo.branch(branch_id)
            if b is None or not b["is_active"]:
                raise UnprocessableError(
                    "Unknown branch", fields={"branch_id": ["Choose one of the active branches"]}
                )
        if assignee_id is not None:
            a = self.repo.assignee(assignee_id)
            if a is None or not a["is_active"]:
                raise UnprocessableError(
                    "Unknown assignee",
                    fields={"assignee_id": ["Choose an active user, or leave the task unassigned"]},
                )

    # ---- reads -----------------------------------------------------------------------------------------------
    def summary(self) -> TaskSummary:
        r = self.repo.summary(dubai_today())
        return TaskSummary(**{k: int(v) for k, v in r.items()})

    def assignees(self) -> list[Assignee]:
        return [Assignee(**r) for r in self.repo.assignees()]

    def search(
        self,
        q: str | None,
        branch_id: uuid.UUID | None,
        all_branches: bool,
        status: str | None,
        assignee_id: uuid.UUID | None,
        unassigned: bool,
        due_from: date | None,
        due_to: date | None,
        view: str | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> TaskPage:
        if due_from and due_to and due_from > due_to:
            raise UnprocessableError(
                "The start of the due-date range is after its end",
                fields={"due_from": ["Start date must not be after the end date"]},
            )
        today = dubai_today()
        rows, total = self.repo.search(
            today, q, branch_id, all_branches, status, assignee_id, unassigned,
            due_from, due_to, view, sort, desc, page, page_size,
        )  # fmt: skip
        return TaskPage(
            items=[self._out(r, today) for r in rows], total=total, page=page, page_size=page_size
        )

    def detail(self, id_: uuid.UUID) -> TaskDetail:
        today = dubai_today()
        return TaskDetail(
            task=self._out(self._load(id_), today),
            history=self.repo.history(id_),  # type: ignore[arg-type]
        )

    # ---- writes ----------------------------------------------------------------------------------------------
    def create(self, body: TaskIn) -> TaskDetail:
        def work() -> uuid.UUID:
            self._check_refs(body.branch_id, body.assignee_id)
            new_id = self.repo.insert(body.model_dump())
            self.session.commit()
            return new_id

        return self.detail(self.run(work))

    def update(self, id_: uuid.UUID, body: TaskUpdate) -> TaskDetail:
        def work() -> None:
            row = self._load(id_, for_update=True)
            self._check_refs(
                body.branch_id if body.branch_id != row["branch_id"] else None,
                body.assignee_id if body.assignee_id != row["assignee_id"] else None,
            )
            self.repo.set_reason(body.reason)
            values = body.model_dump(exclude={"reason"})
            self.repo.update(id_, values)
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    def set_status(self, id_: uuid.UUID, body: StatusIn) -> TaskDetail:
        def work() -> None:
            row = self._load(id_, for_update=True)
            if row["status"] == body.status:
                raise ConflictError(f"The task is already {body.status}", code="status_unchanged")
            self.repo.set_reason(body.note)
            self.repo.set_status(id_, body.status)
            self.session.commit()

        self.run(work)
        return self.detail(id_)
