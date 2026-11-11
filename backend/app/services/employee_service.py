"""Employees, leave management and the six-month rule (BUSINESS_LOGIC §7). Owner-only (RLS + permission checks)."""

import uuid
from datetime import date

from app.core import calculations as calc
from app.core.calculations import money
from app.core.exceptions import ConflictError, UnprocessableError
from app.schemas.hr import (
    ArchiveIn,
    EmployeeDetail,
    EmployeeIn,
    EmployeeOut,
    EmployeePage,
    EmployeeSummary,
    EmployeeUpdate,
    LeaveSummary,
    LeaveUpdateIn,
    ReturnIn,
    StatusChangeIn,
)
from app.services.hr_core import HR_LOCK, HrCore, employee_dict, need_reason, not_found
from app.utils.time import dubai_today

SENSITIVE = ("monthly_salary", "branch_id", "passport_expiry", "visa_expiry")


class EmployeeService(HrCore):
    # ---- reads ---------------------------------------------------------------------------------------------
    def _out(self, row: dict, today: date) -> EmployeeOut:
        return EmployeeOut(**employee_dict(row, today))

    def _load(self, id_: uuid.UUID, today: date, for_update: bool = False) -> dict:
        row = self.hr.employee(id_, today, for_update)
        if row is None:
            raise not_found("Employee")
        return row

    def _open(self, id_: uuid.UUID, today: date) -> dict:
        """Row locked for a write; archived employees are read-only."""
        self.hr.lock(HR_LOCK)
        row = self._load(id_, today, for_update=True)
        if row["archived_at"] is not None:
            raise ConflictError(
                "This employee is archived and can no longer be changed", code="employee_archived"
            )
        return row

    def list(
        self,
        q: str | None,
        branch_id: uuid.UUID | None,
        status: str | None,
        include_archived: bool,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> EmployeePage:
        today = dubai_today()
        rows, total = self.hr.employees(
            today, q, branch_id, status, include_archived, sort, desc, page, page_size
        )
        return EmployeePage(
            items=[self._out(r, today) for r in rows], total=total, page=page, page_size=page_size
        )

    def summary(self) -> EmployeeSummary:
        r = self.hr.employee_summary(dubai_today())
        return EmployeeSummary(
            total_active=int(r["total_active"]),
            on_leave=int(r["on_leave"]),
            close_to_limit=int(r["close_to_limit"]),
            visa_cancelled=int(r["visa_cancelled"]),
            monthly_payroll=money(r["monthly_payroll"]),
            payroll_employees=int(r["payroll_employees"]),
        )

    def leave_summary(self) -> LeaveSummary:
        today = dubai_today()
        c = self.hr.leave_counts(today)
        return LeaveSummary(
            on_leave=int(c["on_leave"]),
            approaching=int(c["approaching"]),
            limit_reached=int(c["limit_reached"]),
            visa_cancelled_by_leave=int(c["visa_cancelled_by_leave"]),
            items=[self._out(r, today) for r in self.hr.leave_watch(today)],
        )

    def detail(self, id_: uuid.UUID) -> EmployeeDetail:
        today = dubai_today()
        row = self._load(id_, today)
        return EmployeeDetail(
            employee=self._out(row, today),
            history=self.hr.record_history("employees", id_),  # type: ignore[arg-type]
        )

    # ---- writes --------------------------------------------------------------------------------------------
    def create(self, body: EmployeeIn) -> EmployeeDetail:
        def work() -> uuid.UUID:
            self.require_branch(body.branch_id)
            new_id = self.hr.insert_employee(body.model_dump())
            self.session.commit()
            return new_id

        return self.detail(self.run(work))

    def update(self, id_: uuid.UUID, body: EmployeeUpdate) -> EmployeeDetail:
        def work() -> None:
            today = dubai_today()
            row = self._open(id_, today)
            new = body.model_dump(exclude={"reason"})
            changed = [f for f in SENSITIVE if new[f] != row[f]]
            if "branch_id" in changed:
                self.require_branch(body.branch_id)
            cur = employee_dict(row, today)
            if cur["visa_cancelled"] and "visa_expiry" in changed:
                raise UnprocessableError(
                    "The visa is cancelled; its expiry date can no longer be changed",
                    fields={"visa_expiry": ["The visa is cancelled"]},
                )
            reason = (
                need_reason(body.reason, "when changing salary, branch or visa/passport dates")
                if changed
                else None
            )
            self.hr.set_reason(reason)
            self.hr.update_employee(id_, new)
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    def change_status(self, id_: uuid.UUID, body: StatusChangeIn) -> EmployeeDetail:
        def work() -> None:
            today = dubai_today()
            row = self._open(id_, today)
            cur = employee_dict(row, today)
            reason = need_reason(body.reason, "for a status change")
            self.hr.set_reason(reason)
            if body.status == "On Leave":
                self._start_leave(id_, row, cur, body.leave_start, today)
            elif body.status == "Active":
                self._return(id_, row, body.return_date, today)
            else:
                self._cancel_visa(id_, row, cur, body.cancellation_date, today)
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    def record_return(self, id_: uuid.UUID, body: ReturnIn) -> EmployeeDetail:
        return self.change_status(
            id_, StatusChangeIn(status="Active", return_date=body.return_date, reason=body.reason)
        )

    def update_leave(self, id_: uuid.UUID, body: LeaveUpdateIn) -> EmployeeDetail:
        def work() -> None:
            today = dubai_today()
            row = self._open(id_, today)
            if row["status"] != "Leave" or row["visa_cancelled"]:
                raise ConflictError("The employee is not on leave", code="not_on_leave")
            self._check_leave_start(body.leave_start, today)
            self.hr.set_reason(need_reason(body.reason, "when correcting the leave start date"))
            self.hr.set_employee_state(
                id_, "Leave", body.leave_start, row["visa_cancelled"], row["visa_cancelled_date"]
            )
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    def archive(self, id_: uuid.UUID, body: ArchiveIn) -> None:
        def work() -> None:
            self._open(id_, dubai_today())
            self.hr.set_reason(body.reason)
            self.hr.archive_employee(id_, body.reason)
            self.session.commit()

        self.run(work)

    # ---- transitions (called inside a locked transaction) --------------------------------------------------
    @staticmethod
    def _check_leave_start(d: date | None, today: date) -> date:
        if d is None:
            raise UnprocessableError(
                "A leave start date is required",
                code="leave_start_required",
                fields={"leave_start": ["Enter the leave start date"]},
            )
        if d > today:
            raise UnprocessableError(
                "The leave start date cannot be in the future (Dubai time)",
                fields={
                    "leave_start": [f"Date cannot be after today in Dubai ({today.isoformat()})"]
                },
            )
        return d

    def _start_leave(
        self, id_: uuid.UUID, row: dict, cur: dict, leave_start: date | None, today: date
    ) -> None:
        if cur["visa_cancelled"]:
            raise ConflictError(
                "The visa is cancelled, so leave cannot be started", code="visa_cancelled"
            )
        if row["status"] == "Leave":
            raise ConflictError("The employee is already on leave", code="already_on_leave")
        start = self._check_leave_start(leave_start, today)
        self.hr.set_employee_state(id_, "Leave", start, False, None)

    def _return(self, id_: uuid.UUID, row: dict, return_date: date | None, today: date) -> None:
        if row["status"] != "Leave":
            raise ConflictError("The employee is not on leave", code="not_on_leave")
        back = return_date or today
        if back > today:
            raise UnprocessableError(
                "The return date cannot be in the future (Dubai time)",
                fields={
                    "return_date": [f"Date cannot be after today in Dubai ({today.isoformat()})"]
                },
            )
        if back < row["leave_start"]:
            raise UnprocessableError(
                "The return date cannot be before the leave start date",
                fields={"return_date": [f"Leave started on {row['leave_start'].isoformat()}"]},
            )
        cancelled, cancelled_date = bool(row["visa_cancelled"]), row["visa_cancelled_date"]
        if not cancelled and calc.returns_after_limit(row["leave_start"], back):
            # Returning after the six-month limit: the cancellation becomes permanent (approved rule, D8).
            cancelled, cancelled_date = True, calc.leave_limit_date(row["leave_start"])
        self.hr.set_employee_state(id_, "Active", None, cancelled, cancelled_date)

    def _cancel_visa(
        self, id_: uuid.UUID, row: dict, cur: dict, when: date | None, today: date
    ) -> None:
        if row["visa_cancelled"]:
            raise ConflictError(
                "The visa is already cancelled (permanent)", code="visa_already_cancelled"
            )
        default = (
            calc.leave_limit_date(row["leave_start"])
            if row["status"] == "Leave" and cur["visa_cancelled"]
            else today
        )
        d = when or default
        if d > today:
            raise UnprocessableError(
                "The cancellation date cannot be in the future (Dubai time)",
                fields={
                    "cancellation_date": [
                        f"Date cannot be after today in Dubai ({today.isoformat()})"
                    ]
                },
            )
        self.hr.set_employee_state(id_, row["status"], row["leave_start"], True, d)
