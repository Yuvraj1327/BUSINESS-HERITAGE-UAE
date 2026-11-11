"""PDC cheques: list/summary, clear (ledger-backed, exactly once), bounce, replace, edit a pending cheque. Owner-only."""

import uuid
from datetime import date

from app.core.calculations import money
from app.core.exceptions import ConflictError, UnprocessableError
from app.schemas.rentals import (
    BounceIn,
    ChequeDetail,
    ChequeOut,
    ChequePage,
    ChequeSummary,
    ChequeUpdate,
    ClearIn,
    ReplaceIn,
)
from app.services.agreement_service import RENTAL_LOCK
from app.services.rental_core import RentalCore, agreement_dict, cheque_dict, need_reason, not_found
from app.utils.time import dubai_today


class ChequeService(RentalCore):
    def _out(self, row: dict, today: date) -> ChequeOut:
        return ChequeOut(**cheque_dict(row, today, self.rent.tracking_start()))

    def _load(self, id_: uuid.UUID, for_update: bool = False) -> dict:
        row = self.rent.cheque(id_, for_update)
        if row is None:
            raise not_found("Cheque")
        return row

    # ---- reads -----------------------------------------------------------------------------------------------
    def search(
        self,
        q: str | None,
        branch_id: uuid.UUID | None,
        bank: str | None,
        status: str | None,
        view: str | None,
        date_from: date | None,
        date_to: date | None,
        agreement_id: uuid.UUID | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> ChequePage:
        today = dubai_today()
        if date_from and date_to and date_from > date_to:
            raise UnprocessableError(
                "The start of the date range is after its end",
                fields={"date_from": ["Start date must not be after the end date"]},
            )
        rows, total = self.rent.cheques(
            today,
            q,
            branch_id,
            bank,
            status,
            view,
            date_from,
            date_to,
            agreement_id,
            sort,
            desc,
            page,
            page_size,
        )
        start = self.rent.tracking_start()
        return ChequePage(
            items=[ChequeOut(**cheque_dict(r, today, start)) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def summary(self) -> ChequeSummary:
        today = dubai_today()
        s = self.rent.cheque_summary(today)
        nxt = self.rent.next_cheque(today)
        return ChequeSummary(
            pending_count=int(s["pending_count"]),
            due_30_count=int(s["due_30_count"]),
            overdue_count=int(s["overdue_count"]),
            cleared_count=int(s["cleared_count"]),
            bounced_count=int(s["bounced_count"]),
            pending_amount=money(s["pending_amount"]),
            bounced_amount=money(s["bounced_amount"]),
            bounced_unresolved_count=int(s["bounced_unresolved_count"]),
            bounced_unresolved_amount=money(s["bounced_unresolved_amount"]),
            next_cheque=self._out(nxt, today) if nxt else None,
        )

    def detail(self, id_: uuid.UUID) -> ChequeDetail:
        today = dubai_today()
        row = self._load(id_)
        ag = self.rent.agreement(row["agreement_id"], today)
        assert ag is not None
        from app.schemas.rentals import AgreementOut

        return ChequeDetail(
            cheque=self._out(row, today),
            agreement=AgreementOut(**agreement_dict(ag, today)),
            history=self.rent.record_history("pdc_cheques", id_),  # type: ignore[arg-type]
        )

    # ---- clear -----------------------------------------------------------------------------------------------
    def clear(self, id_: uuid.UUID, body: ClearIn) -> ChequeDetail:
        def work() -> None:
            self.fin.lock()  # the same advisory lock every Step 8 money movement takes
            today = dubai_today()
            start = self.require_configured()
            row = self._load(id_, for_update=True)
            if row["status"] != "Pending":
                raise ConflictError(
                    f"This cheque is already {row['status'].lower()}; it cannot be cleared again",
                    code="cheque_not_pending",
                )
            cleared_on = body.cleared_date or today
            if cleared_on > today:
                raise UnprocessableError(
                    "The cleared date cannot be in the future (Dubai time)",
                    fields={
                        "cleared_date": [f"Cannot be after today in Dubai ({today.isoformat()})"]
                    },
                )
            if cleared_on < start:
                raise UnprocessableError(
                    "The cleared date is before financial tracking started",
                    fields={"cleared_date": [f"Tracking started on {start.isoformat()}"]},
                )
            self.rent.set_reason(body.note)
            self.rent.mark_cleared(
                id_, cleared_on
            )  # the ledger row appears on the cheque date, exactly once
            self.session.flush()
            # No-overdraft policy (Step 8): the bank may not end negative on the cheque date or today.
            for d in {row["cheque_date"], today}:
                if d < start:
                    continue
                if money(self.rent.bank_balance(row["bank"], d)) < 0:
                    raise UnprocessableError(
                        f"{row['bank']} does not have enough balance to clear this cheque",
                        code="insufficient_funds",
                    )
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    # ---- bounce ----------------------------------------------------------------------------------------------
    def bounce(self, id_: uuid.UUID, body: BounceIn) -> ChequeDetail:
        def work() -> None:
            self.rent.lock(RENTAL_LOCK)
            today = dubai_today()
            row = self._load(id_, for_update=True)
            if row["status"] != "Pending":
                raise ConflictError(
                    f"This cheque is already {row['status'].lower()}; it cannot be marked bounced",
                    code="cheque_not_pending",
                )
            self.rent.set_reason(need_reason(body.reason, "to mark a cheque bounced"))
            self.rent.mark_bounced(
                id_, body.bounced_date or today
            )  # no ledger row: not a bank deduction
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    # ---- replace a bounced cheque --------------------------------------------------------------------------
    def replace(self, id_: uuid.UUID, body: ReplaceIn) -> ChequeDetail:
        def work() -> uuid.UUID:
            self.rent.lock(RENTAL_LOCK)
            today = dubai_today()
            row = self._load(id_, for_update=True)
            if row["status"] != "Bounced":
                raise ConflictError(
                    "Only a bounced cheque can be replaced", code="cheque_not_bounced"
                )
            if row["replaced_by_id"] is not None:
                raise ConflictError(
                    "This bounced cheque already has a replacement", code="already_replaced"
                )
            self.rent.set_reason(need_reason(body.reason, "to replace a bounced cheque"))
            new_id = self.rent.insert_cheque(
                {
                    "agreement_id": row["agreement_id"],
                    "cheque_no": body.cheque_no.strip(),
                    "bank": body.bank or row["bank"],
                    "cheque_date": body.cheque_date or today,
                    "amount": row[
                        "amount"
                    ],  # same amount: the schedule total keeps equalling the annual rent
                    "notes": body.notes,
                    "replaces_id": id_,
                }
            )
            self.session.commit()
            return new_id

        return self.detail(self.run(work))

    # ---- edit a pending cheque -----------------------------------------------------------------------------
    def update(self, id_: uuid.UUID, body: ChequeUpdate) -> ChequeDetail:
        def work() -> None:
            self.rent.lock(RENTAL_LOCK)
            row = self._load(id_, for_update=True)
            if row["status"] != "Pending":
                raise ConflictError(
                    f"A {row['status'].lower()} cheque is final and cannot be edited",
                    code="cheque_immutable",
                )
            self.rent.set_reason(need_reason(body.reason, "to change a cheque"))
            self.rent.update_pending_cheque(
                id_,
                {
                    "cheque_no": body.cheque_no.strip(),
                    "cheque_date": body.cheque_date,
                    "bank": body.bank,
                    "notes": body.notes,
                },
            )
            self.session.commit()

        self.run(work)
        return self.detail(id_)
