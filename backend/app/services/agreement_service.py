"""Rental agreements: create with a reviewed cheque schedule, update, renewal (BUSINESS_LOGIC section 9). Owner-only."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from app.core import rentals as rules
from app.core.calculations import money
from app.core.exceptions import ConflictError, UnprocessableError
from app.schemas.rentals import (
    AgreementDetail,
    AgreementIn,
    AgreementOut,
    AgreementPage,
    AgreementUpdate,
    ChequeOut,
    RenewalLink,
    RenewalPreview,
    RenewConfirmIn,
    RenewIn,
    ScheduleLine,
    ScheduleOut,
    SchedulePreview,
)
from app.services.rental_core import (
    RentalCore,
    agreement_dict,
    cheque_dict,
    need_reason,
    not_found,
)
from app.utils.time import dubai_today

RENTAL_LOCK = 80903  # serialises agreement writes and renewals


def preview_of(
    lines: list[rules.ChequeLine], rent: Decimal, end: date | None = None
) -> SchedulePreview:
    total = sum((ln.amount for ln in lines), Decimal("0.00"))
    return SchedulePreview(
        lines=[
            ScheduleLine(
                seq=ln.seq,
                cheque_no=ln.cheque_no,
                cheque_date=ln.cheque_date,
                amount=ln.amount,
                bank=ln.bank,  # type: ignore[arg-type]
            )
            for ln in lines
        ],
        annual_rent=money(rent),
        total_cheque_value=money(total),
        cheque_count=len(lines),
        matches=money(total) == money(rent),
        end_date=end,
    )


class AgreementService(RentalCore):
    # ---- reads ---------------------------------------------------------------------------------------------
    def _out(self, row: dict, today: date) -> AgreementOut:
        return AgreementOut(**agreement_dict(row, today))

    def _load(self, id_: uuid.UUID, today: date, for_update: bool = False) -> dict:
        row = self.rent.agreement(id_, today, for_update)
        if row is None:
            raise not_found("Rental agreement")
        return row

    def _open(self, id_: uuid.UUID, today: date) -> dict:
        self.rent.lock(RENTAL_LOCK)
        row = self._load(id_, today, for_update=True)
        if row["status"] != "Active":
            raise ConflictError(
                f"This agreement is {row['status'].lower()} and can no longer be changed",
                code="agreement_closed",
            )
        return row

    def preview(self, p: Any) -> SchedulePreview:
        lines = self.build_lines(
            p.annual_rent, p.cheque_count, p.first_cheque_date, p.first_cheque_no, p.bank, None
        )
        return preview_of(lines, p.annual_rent)

    def search(
        self,
        q: str | None,
        branch_id: uuid.UUID | None,
        status: str | None,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
        upcoming_days: int | None = None,
    ) -> AgreementPage:
        today = dubai_today()
        rows, total = self.rent.agreements(
            today, q, branch_id, status, sort, desc, page, page_size, upcoming_days
        )
        return AgreementPage(
            items=[self._out(r, today) for r in rows], total=total, page=page, page_size=page_size
        )

    def _schedule(self, agreement: dict, today: date) -> ScheduleOut:
        start = self.rent.tracking_start()
        rows = self.rent.agreement_cheques(agreement["id"])
        items = [ChequeOut(**cheque_dict(r, today, start)) for r in rows]
        live = [c for c in items if not c.superseded]
        total = sum((c.amount for c in live), Decimal("0.00"))
        return ScheduleOut(
            agreement_id=agreement["id"],
            annual_rent=money(agreement["annual_rent"]),
            total_cheque_value=money(total),
            cheque_count=len(live),
            matches=money(total) == money(agreement["annual_rent"]),
            pending=sum(1 for c in items if c.status == "Pending"),
            cleared=sum(1 for c in items if c.status == "Cleared"),
            bounced=sum(1 for c in items if c.status == "Bounced"),
            items=items,
        )

    def schedule(self, id_: uuid.UUID) -> ScheduleOut:
        today = dubai_today()
        return self._schedule(self._load(id_, today), today)

    def _links(self, id_: uuid.UUID, today: date) -> list[RenewalLink]:
        return [
            RenewalLink(
                id=r["id"],
                relation=r["relation"],
                start_date=r["start_date"],
                end_date=r["end_date"],
                annual_rent=money(r["annual_rent"]),
                cheque_count=r["cheque_count"],
                status=rules.agreement_status(r["status"], r["start_date"], r["end_date"], today),
            )
            for r in self._chain(id_)
        ]

    def renewals(self, id_: uuid.UUID) -> list[RenewalLink]:
        today = dubai_today()
        self._load(id_, today)
        return self._links(id_, today)

    def _chain(self, id_: uuid.UUID) -> list[dict]:
        out: list[dict] = []
        seen_current = False
        for r in self.rent.renewal_chain(id_):
            row = dict(r)
            if row["is_current"]:
                seen_current = True
            row["relation"] = (
                "current" if row["is_current"] else ("next" if seen_current else "previous")
            )
            out.append(row)
        return out

    def detail(self, id_: uuid.UUID) -> AgreementDetail:
        today = dubai_today()
        row = self._load(id_, today)
        return AgreementDetail(
            agreement=self._out(row, today),
            schedule=self._schedule(row, today),
            renewals=self._links(id_, today),
            history=self.rent.record_history("rental_agreements", id_),  # type: ignore[arg-type]
        )

    # ---- create (the confirmed schedule) -----------------------------------------------------------------------
    def create(self, body: AgreementIn) -> AgreementDetail:
        def work() -> uuid.UUID:
            self.rent.lock(RENTAL_LOCK)
            self.require_branch(body.branch_id)
            end = body.end_date or rules.agreement_end_date(body.start_date)
            if end <= body.start_date:
                raise UnprocessableError(
                    "The agreement end date must be after the start date",
                    fields={"end_date": ["End date must be after the start date"]},
                )
            lines = self.build_lines(
                body.annual_rent,
                body.cheque_count,
                body.first_cheque_date,
                body.first_cheque_no,
                body.bank,
                body.cheques,
            )
            new_id = self.rent.insert_agreement(
                {
                    "branch_id": body.branch_id,
                    "landlord": body.landlord,
                    "unit": body.unit,
                    "start_date": body.start_date,
                    "end_date": end,
                    "annual_rent": money(body.annual_rent),
                    "bank": body.bank,
                    "cheque_count": body.cheque_count,
                    "first_cheque_date": body.first_cheque_date,
                    "first_cheque_no": body.first_cheque_no,
                    "notes": body.notes,
                    "renewed_from_id": None,
                }
            )
            self.insert_schedule(new_id, lines)
            self.session.commit()
            return new_id

        return self.detail(self.run(work))

    # ---- update --------------------------------------------------------------------------------------------
    def update(self, id_: uuid.UUID, body: AgreementUpdate) -> AgreementDetail:
        def work() -> None:
            today = dubai_today()
            row = self._open(id_, today)
            changed = (
                body.branch_id != row["branch_id"]
                or body.start_date != row["start_date"]
                or body.end_date != row["end_date"]
            )
            if body.branch_id != row["branch_id"]:
                self.require_branch(body.branch_id)
            reason = (
                need_reason(body.reason, "when changing the branch or the agreement dates")
                if changed
                else None
            )
            self.rent.set_reason(reason)
            self.rent.update_agreement(
                id_,
                {
                    "branch_id": body.branch_id,
                    "landlord": body.landlord,
                    "unit": body.unit,
                    "start_date": body.start_date,
                    "end_date": body.end_date,
                    "notes": body.notes,
                },
            )
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    # ---- renewal -------------------------------------------------------------------------------------------
    def _renewal_plan(
        self, row: dict, body: RenewIn, today: date
    ) -> tuple[dict[str, Any], list[rules.ChequeLine]]:
        cheques = self.rent.agreement_cheques(row["id"])
        if not cheques:
            raise ConflictError("The agreement has no cheques to continue", code="no_cheques")
        live = [c for c in cheques if not c["superseded"]]
        first = min(live or cheques, key=lambda c: (c["cheque_date"], c["cheque_no"]))
        n = body.cheque_count or row["cheque_count"] or len(live)
        bank = body.bank or row["bank"] or first["bank"]
        rent = body.annual_rent if body.annual_rent is not None else row["annual_rent"]
        start, end = rules.renewal_dates(row["end_date"])
        series_start = row["first_cheque_no"] or first["cheque_no"]
        try:
            first_no = body.first_cheque_no or rules.next_cheque_no(
                [c["cheque_no"] for c in cheques], series_start
            )
        except rules.ScheduleError as e:
            raise self.schedule_error(e) from e
        first_date = body.first_cheque_date or start
        lines = self.build_lines(rent, n, first_date, first_no, bank, body.cheques)
        plan = {
            "start_date": start,
            "end_date": end,
            "annual_rent": money(rent),
            "cheque_count": n,
            "first_cheque_no": lines[0].cheque_no if body.cheques else first_no,
            "first_cheque_date": lines[0].cheque_date if body.cheques else first_date,
            "bank": bank,
        }
        return plan, lines

    def renewal_preview(self, id_: uuid.UUID, body: RenewIn) -> RenewalPreview:
        today = dubai_today()
        row = self._load(id_, today)
        if row["status"] != "Active" or row["renewed_to_id"] is not None:
            raise ConflictError(
                "Only an active agreement that has not been renewed can be renewed",
                code="not_renewable",
            )
        plan, lines = self._renewal_plan(row, body, today)
        return RenewalPreview(
            old=self._out(row, today),
            old_annual_rent=money(row["annual_rent"]),
            old_pending_cheques=int(row["pending_count"]),
            schedule=preview_of(lines, plan["annual_rent"], plan["end_date"]),
            **plan,
        )

    def renew(self, id_: uuid.UUID, body: RenewConfirmIn) -> AgreementDetail:
        if not body.confirm:
            raise UnprocessableError(
                "Renewal must be confirmed",
                code="confirmation_required",
                fields={"confirm": ["Confirm the renewal"]},
            )

        def work() -> uuid.UUID:
            today = dubai_today()
            row = self._open(id_, today)
            if row["end_date"] != body.expected_end_date:
                raise ConflictError(
                    "This agreement was already renewed or changed. Reload before renewing again.",
                    code="stale_renewal",
                    fields={
                        "expected_end_date": [
                            f"The current end date is {row['end_date'].isoformat()}"
                        ]
                    },
                )
            if row["renewed_to_id"] is not None:
                raise ConflictError(
                    "This agreement has already been renewed", code="already_renewed"
                )
            plan, lines = self._renewal_plan(row, body, today)
            total = sum((ln.amount for ln in lines), Decimal("0.00"))
            if (
                total != plan["annual_rent"]
            ):  # defence in depth: build_lines already guarantees this
                raise UnprocessableError("The new cheque total must equal the new annual rent")
            self.require_branch(row["branch_id"])
            self.rent.set_reason(
                f"Renewed: new agreement {plan['start_date']} to {plan['end_date']}"
            )
            new_id = self.rent.insert_agreement(
                {
                    "branch_id": row["branch_id"],
                    "landlord": row["landlord"],
                    "unit": row["unit"],
                    "start_date": plan["start_date"],
                    "end_date": plan["end_date"],
                    "annual_rent": plan["annual_rent"],
                    "bank": plan["bank"],
                    "cheque_count": plan["cheque_count"],
                    "first_cheque_date": plan["first_cheque_date"],
                    "first_cheque_no": plan["first_cheque_no"],
                    "notes": body.notes,
                    "renewed_from_id": id_,
                }
            )
            self.insert_schedule(
                new_id, lines
            )  # every new cheque starts Pending; old cheques are untouched
            self.rent.set_agreement_status(id_, "Renewed")
            self.session.commit()
            return new_id

        return self.detail(self.run(work))
