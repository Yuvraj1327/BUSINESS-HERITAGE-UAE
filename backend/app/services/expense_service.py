import uuid
from datetime import date
from typing import Any

from app.core import calculations as calc
from app.core.calculations import money
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.repositories.finance_repository import API_ACCOUNT, DB_ACCOUNT
from app.schemas.finance import (
    AuditEntry,
    ExpenseCategoryOut,
    ExpenseCorrectionIn,
    ExpenseDetail,
    ExpenseIn,
    ExpenseOut,
    ExpensePage,
    ExpenseTotals,
)
from app.services.finance_core import FinanceCore


def expense_out(r: dict[str, Any]) -> ExpenseOut:
    return ExpenseOut(
        id=r["id"],
        expense_date=r["expense_date"],
        branch_id=r["branch_id"],
        branch_name=r["branch_name"],
        category_id=r["category_id"],
        category=r["category"],
        amount=r["amount"],
        paid_from=API_ACCOUNT[r["paid_from"]],  # type: ignore[arg-type]
        note=r["note"],
        is_saving=r["is_saving"],
        voided=r["voided"],
        void_reason=r["void_reason"],
        corrects_id=r["corrects_id"],
        created_at=r["created_at"],
        created_by_name=r["created_by_name"],
    )


class ExpenseService(FinanceCore):
    def categories(self) -> list[ExpenseCategoryOut]:
        return [ExpenseCategoryOut(**r) for r in self.fin.categories()]

    def list(
        self,
        d_from: date | None,
        d_to: date | None,
        branch: uuid.UUID | None,
        all_branches_only: bool,
        category: uuid.UUID | None,
        paid_from: str | None,
        is_saving: bool | None,
        include_voided: bool,
        page: int,
        page_size: int,
    ) -> ExpensePage:
        if d_from and d_to and d_from > d_to:
            raise UnprocessableError(
                "Start date is after end date",
                fields={"date_from": ["Start date must not be after end date"]},
            )
        f = {
            "d_from": d_from,
            "d_to": d_to,
            "branch": branch,
            "all_only": all_branches_only,
            "cat": category,
            "pf": DB_ACCOUNT[paid_from] if paid_from else None,
            "sav": is_saving,
            "voided": include_voided,
        }
        rows, agg = self.fin.expenses_page(f, page_size, (page - 1) * page_size)
        total, savings = money(agg["total"]), money(agg["savings"])
        return ExpensePage(
            items=[expense_out(r) for r in rows],
            total=int(agg["n"]),
            page=page,
            page_size=page_size,
            totals=ExpenseTotals(
                total=total,
                savings=savings,
                excl_savings=calc.head_office_excl_savings(total, savings),
                count=int(agg["active"]),
            ),
        )

    def get(self, id_: uuid.UUID) -> ExpenseDetail:
        row = self.fin.expense(id_)
        if row is None:
            raise NotFoundError("Expense not found")
        history = [AuditEntry(**h) for h in self.fin.record_history("head_office_expenses", id_)]
        return ExpenseDetail(expense=expense_out(row), history=history)

    def _check_refs(self, body: ExpenseIn) -> None:
        cat = self.fin.category(body.category_id)
        if cat is None or not cat["is_active"]:
            raise UnprocessableError(
                "Unknown expense category", fields={"category_id": ["Select a category"]}
            )
        if body.branch_id is not None:
            br = self.fin.branch(body.branch_id)
            if br is None or not br["is_active"]:
                raise UnprocessableError(
                    "Unknown or inactive branch",
                    fields={"branch_id": ["Select a branch or All branches"]},
                )

    def _values(self, body: ExpenseIn, d: date, corrects: uuid.UUID | None) -> dict[str, Any]:
        return {
            "expense_date": d,
            "branch_id": body.branch_id,
            "category_id": body.category_id,
            "amount": body.amount,
            "paid_from": DB_ACCOUNT[body.paid_from],
            "note": body.note or None,
            "is_saving": body.is_saving,
            "client_key": body.client_key,
            "corrects_id": corrects,
        }

    def create(self, body: ExpenseIn) -> ExpenseOut:
        def work() -> uuid.UUID:
            self.fin.lock()
            d = self.resolve_date(body.expense_date, "expense_date")
            self._check_refs(body)
            self.ensure_funds(body.paid_from, body.amount, d)
            new_id = self.fin.insert_expense(self._values(body, d, None))
            self.session.commit()
            return new_id

        return self._out(self.run(work))

    def correct(self, id_: uuid.UUID, body: ExpenseCorrectionIn) -> ExpenseOut:
        """Owner correction (decision D4): the original is voided with the reason and a corrected row is created,
        atomically, linked by corrects_id. Nothing is overwritten, so history and audit stay complete."""

        def work() -> uuid.UUID:
            self.fin.lock()
            old = self.fin.expense(id_)
            if old is None:
                raise NotFoundError("Expense not found")
            if old["voided"]:
                raise ConflictError("This expense is already voided", code="already_voided")
            d = self.resolve_date(body.expense_date, "expense_date")
            self._check_refs(body)
            self.fin.void_ledger("void_head_office_expense", id_, f"Corrected: {body.reason}")
            self.ensure_funds(body.paid_from, body.amount, d)
            new_id = self.fin.insert_expense(self._values(body, d, id_))
            self.session.commit()
            return new_id

        return self._out(self.run(work))

    def void(self, id_: uuid.UUID, reason: str) -> None:
        def work() -> None:
            self.fin.lock()
            if self.fin.expense(id_) is None:
                raise NotFoundError("Expense not found")
            self.fin.void_ledger("void_head_office_expense", id_, reason)
            self.session.commit()

        self.run(work)

    def set_saving(self, id_: uuid.UUID, is_saving: bool, reason: str) -> ExpenseOut:
        def work() -> None:
            self.fin.lock()
            old = self.fin.expense(id_)
            if old is None:
                raise NotFoundError("Expense not found")
            if old["voided"]:
                raise ConflictError("A voided expense cannot be changed", code="already_voided")
            if old["is_saving"] == is_saving:
                raise ConflictError("The expense already has this saving status", code="no_change")
            self.fin.set_reason(reason)
            self.fin.set_saving(id_, is_saving)
            self.session.commit()

        self.run(work)
        return self._out(id_)

    def _out(self, id_: uuid.UUID) -> ExpenseOut:
        row = self.fin.expense(id_)
        assert row is not None
        return expense_out(row)
