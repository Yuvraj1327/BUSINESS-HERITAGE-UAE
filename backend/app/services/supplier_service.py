import uuid
from datetime import date
from typing import Any

from app.core.calculations import money, supplier_outstanding
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
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
)
from app.services.finance_core import FinanceCore


def supplier_out(r: dict[str, Any]) -> SupplierOut:
    return SupplierOut(
        id=r["id"],
        name=r["name"],
        category=r["category"],
        payment_terms=r["payment_terms"],
        notes=r["notes"],
        is_active=r["is_active"],
        opening_outstanding=r["opening_outstanding"],
        new_dues=r["new_dues"],
        total_paid=r["total_paid"],
        outstanding=supplier_outstanding(r["opening_outstanding"], r["new_dues"], r["total_paid"]),
        created_at=r["created_at"],
    )


class SupplierService(FinanceCore):
    def summary(self) -> SupplierSummary:
        r = self.fin.supplier_summary()
        return SupplierSummary(
            total_suppliers=int(r["total_suppliers"]),
            total_outstanding=money(r["total_outstanding"]),
            total_paid=money(r["total_paid"]),
            with_outstanding=int(r["with_outstanding"]),
        )

    def list(
        self,
        search: str | None,
        status: str,
        owing: bool,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> SupplierPage:
        rows, total = self.fin.suppliers_page(
            search or None, status, owing, sort, desc, page_size, (page - 1) * page_size
        )
        return SupplierPage(
            items=[supplier_out(r) for r in rows], total=total, page=page, page_size=page_size
        )

    def get(self, id_: uuid.UUID) -> SupplierOut:
        r = self.fin.supplier(id_)
        if r is None:
            raise NotFoundError("Supplier not found")
        return supplier_out(r)

    def create(self, body: SupplierIn) -> SupplierOut:
        if body.opening_outstanding and self.tracking_start() is not None:
            raise UnprocessableError(
                "Opening dues can only be entered before opening balances are saved; record a new due instead",
                fields={
                    "opening_outstanding": [
                        "Use 'Record new due' (or correct the Opening Balances)"
                    ]
                },
            )

        def work() -> uuid.UUID:
            new_id = self.fin.insert_supplier(
                {
                    "name": body.name,
                    "category": body.category,
                    "payment_terms": body.payment_terms,
                    "notes": body.notes,
                    "is_active": body.is_active,
                    "opening": body.opening_outstanding or 0,
                }
            )
            self.session.commit()
            return new_id

        return self.get(self.run(work))

    def update(self, id_: uuid.UUID, body: SupplierUpdate) -> SupplierOut:
        def work() -> None:
            if self.fin.update_supplier(id_, body.model_dump()) == 0:
                raise NotFoundError("Supplier not found")
            self.session.commit()

        self.run(work)
        return self.get(id_)

    # ---- ledger ------------------------------------------------------------------------------------------
    def entries(
        self,
        id_: uuid.UUID,
        kind: str | None,
        d_from: date | None,
        d_to: date | None,
        page: int,
        page_size: int,
    ) -> SupplierEntryPage:
        if self.fin.supplier(id_) is None:
            raise NotFoundError("Supplier not found")
        if d_from and d_to and d_from > d_to:
            raise UnprocessableError(
                "Start date is after end date",
                fields={"date_from": ["Start date must not be after end date"]},
            )
        rows, total = self.fin.entries_page(
            id_, kind, d_from, d_to, page_size, (page - 1) * page_size
        )
        return SupplierEntryPage(
            items=[SupplierEntryOut(**r) for r in rows], total=total, page=page, page_size=page_size
        )

    def record_due(self, id_: uuid.UUID, body: SupplierDueIn) -> SupplierEntryOut:
        def work() -> uuid.UUID:
            self.fin.lock()
            sup = self.fin.supplier(id_)
            if sup is None:
                raise NotFoundError("Supplier not found")
            if not sup["is_active"]:
                raise ConflictError("This supplier is inactive", code="supplier_inactive")
            d = self.resolve_date(body.entry_date, "entry_date")
            new_id = self.fin.insert_entry(
                {
                    "supplier_id": id_,
                    "entry_date": d,
                    "kind": "due",
                    "amount": body.amount,
                    "paid_from": None,
                    "branch_id": None,
                    "reference": body.reference,
                    "note": body.note,
                    "client_key": body.client_key,
                }
            )
            self.session.commit()
            return new_id

        return self._entry(self.run(work))

    def pay(self, id_: uuid.UUID, body: SupplierPaymentIn) -> SupplierEntryOut:
        if body.branch_id is not None and body.paid_from != "Cash":
            raise UnprocessableError(
                "A branch applies to cash payments only",
                fields={"branch_id": ["Only for cash payments"]},
            )

        def work() -> uuid.UUID:
            self.fin.lock()
            return self._pay(
                id_,
                body.amount,
                body.payment_date,
                body.paid_from,
                body.branch_id,
                body.reference,
                body.note,
                body.client_key,
            )

        return self._entry(self.run(work))

    def mark_paid(self, id_: uuid.UUID, body: MarkPaidIn) -> SupplierEntryOut:
        if body.branch_id is not None and body.paid_from != "Cash":
            raise UnprocessableError(
                "A branch applies to cash payments only",
                fields={"branch_id": ["Only for cash payments"]},
            )

        def work() -> uuid.UUID:
            self.fin.lock()
            sup = self.fin.supplier(id_)
            if sup is None:
                raise NotFoundError("Supplier not found")
            amount = supplier_outstanding(
                sup["opening_outstanding"], sup["new_dues"], sup["total_paid"]
            )
            if amount <= 0:
                raise ConflictError(
                    "Nothing is outstanding for this supplier", code="nothing_outstanding"
                )
            note = body.note or "Marked as paid (full outstanding amount)"
            return self._pay(
                id_,
                amount,
                body.payment_date,
                body.paid_from,
                body.branch_id,
                body.reference,
                note,
                body.client_key,
            )

        return self._entry(self.run(work))

    def _pay(
        self,
        id_: uuid.UUID,
        amount: Any,
        when: date | None,
        paid_from: str,
        branch: uuid.UUID | None,
        reference: str | None,
        note: str | None,
        client_key: uuid.UUID | None,
    ) -> uuid.UUID:
        sup = self.fin.supplier(id_)
        if sup is None:
            raise NotFoundError("Supplier not found")
        d = self.resolve_date(when, "payment_date")
        owed = supplier_outstanding(sup["opening_outstanding"], sup["new_dues"], sup["total_paid"])
        if amount > owed:
            raise UnprocessableError(
                f"Payment exceeds the outstanding amount ({owed} AED)",
                code="exceeds_outstanding",
                fields={"amount": [f"At most {owed} AED is outstanding"]},
            )
        if branch is not None:
            br = self.fin.branch(branch)
            if br is None or not br["is_active"]:
                raise UnprocessableError(
                    "Unknown or inactive branch", fields={"branch_id": ["Select an active branch"]}
                )
        self.ensure_funds(paid_from, amount, d)
        new_id = self.fin.insert_entry(
            {
                "supplier_id": id_,
                "entry_date": d,
                "kind": "payment",
                "amount": amount,
                "paid_from": paid_from,
                "branch_id": branch,
                "reference": reference,
                "note": note,
                "client_key": client_key,
            }
        )
        self.session.commit()
        return new_id

    def void_entry(self, entry_id: uuid.UUID, reason: str) -> None:
        def work() -> None:
            self.fin.lock()
            if self.fin.entry(entry_id) is None:
                raise NotFoundError("Supplier entry not found")
            self.fin.void_ledger("void_supplier_entry", entry_id, reason)
            self.ensure_no_negative_balances()
            self.session.commit()

        self.run(work)

    def _entry(self, id_: uuid.UUID) -> SupplierEntryOut:
        row = self.fin.entry(id_)
        assert row is not None
        return SupplierEntryOut(**row)
