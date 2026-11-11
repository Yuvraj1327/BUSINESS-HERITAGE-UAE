"""Trade licences and renewals. Renewal = previous expiry + 1 year; history kept; repeat clicks refused."""

import uuid

from app.core import calculations as calc
from app.core.calculations import money
from app.core.exceptions import ConflictError, UnprocessableError
from app.schemas.hr import (
    ArchiveIn,
    LicenseDetail,
    LicenseIn,
    LicenseOut,
    LicensePage,
    LicenseSummary,
    LicenseUpdate,
    RenewalOut,
    RenewIn,
)
from app.services.hr_core import HR_LOCK, HrCore, license_dict, need_reason, not_found
from app.utils.time import dubai_today


class LicenseService(HrCore):
    def _out(self, row: dict) -> LicenseOut:
        return LicenseOut(**license_dict(row, dubai_today()))

    def _load(self, id_: uuid.UUID, for_update: bool = False) -> dict:
        row = self.hr.license(id_, for_update)
        if row is None:
            raise not_found("Trade licence")
        return row

    def _open(self, id_: uuid.UUID) -> dict:
        self.hr.lock(HR_LOCK)
        row = self._load(id_, for_update=True)
        if row["archived_at"] is not None:
            raise ConflictError(
                "This licence is archived and can no longer be changed", code="license_archived"
            )
        return row

    def search(
        self,
        q: str | None,
        branch_id: uuid.UUID | None,
        status: str | None,
        include_archived: bool,
        sort: str,
        desc: bool,
        page: int,
        page_size: int,
    ) -> LicensePage:
        rows, total = self.hr.licenses(
            dubai_today(), q, branch_id, status, include_archived, sort, desc, page, page_size
        )
        return LicensePage(
            items=[self._out(r) for r in rows], total=total, page=page, page_size=page_size
        )

    def summary(self) -> LicenseSummary:
        r = self.hr.license_summary(dubai_today())
        return LicenseSummary(
            total=int(r["total"]),
            expired=int(r["expired"]),
            expiring_30=int(r["expiring_30"]),
            expiring_60=int(r["expiring_60"]),
            renewal_fees_due=money(r["renewal_fees_due"]),
            fees_due_count=int(r["fees_due_count"]),
        )

    def renewals(self, id_: uuid.UUID) -> list[RenewalOut]:
        self._load(id_)
        return [RenewalOut(**r) for r in self.hr.renewals(id_)]

    def detail(self, id_: uuid.UUID) -> LicenseDetail:
        row = self._load(id_)
        return LicenseDetail(
            license=self._out(row),
            renewals=[RenewalOut(**r) for r in self.hr.renewals(id_)],
            history=self.hr.record_history("trade_licenses", id_),  # type: ignore[arg-type]
        )

    def create(self, body: LicenseIn) -> LicenseDetail:
        def work() -> uuid.UUID:
            self.require_branch(body.branch_id)
            new_id = self.hr.insert_license(body.model_dump())
            self.session.commit()
            return new_id

        return self.detail(self.run(work))

    def update(self, id_: uuid.UUID, body: LicenseUpdate) -> LicenseDetail:
        def work() -> None:
            row = self._open(id_)
            new = body.model_dump(exclude={"reason"})
            changed = [
                f
                for f in ("branch_id", "license_no", "expiry_date", "renewal_fee")
                if new[f] != row[f]
            ]
            if "branch_id" in changed:
                self.require_branch(body.branch_id)
            if "expiry_date" in changed:
                # Expiry normally moves only through a recorded renewal; a manual correction needs a reason.
                self.hr.set_reason(
                    need_reason(body.reason, "when correcting a licence expiry date")
                )
            elif changed:
                self.hr.set_reason(need_reason(body.reason, "when changing licence details"))
            self.hr.update_license(id_, new)
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    def renew(self, id_: uuid.UUID, body: RenewIn) -> LicenseDetail:
        def work() -> None:
            today = dubai_today()
            row = self._open(id_)
            if row["expiry_date"] != body.expected_expiry:
                raise ConflictError(
                    "This licence was already renewed or changed. Reload before renewing again.",
                    code="stale_renewal",
                    fields={
                        "expected_expiry": [
                            f"The current expiry is {row['expiry_date'].isoformat()}"
                        ]
                    },
                )
            new_expiry = calc.add_one_year(row["expiry_date"])
            fee = body.renewal_fee if body.renewal_fee is not None else row["renewal_fee"]
            if fee < 0:
                raise UnprocessableError("The renewal fee cannot be negative")
            self.hr.set_reason(f"Renewed to {new_expiry.isoformat()}")
            self.hr.insert_renewal(
                {
                    "license_id": id_,
                    "renewed_on": today,
                    "previous_expiry": row["expiry_date"],
                    "new_expiry": new_expiry,
                    "renewal_fee": fee,
                    "note": body.note,
                    "client_key": body.client_key,
                }
            )
            self.hr.set_license_expiry(id_, new_expiry)
            self.session.commit()

        self.run(work)
        return self.detail(id_)

    def archive(self, id_: uuid.UUID, body: ArchiveIn) -> None:
        def work() -> None:
            self._open(id_)
            self.hr.set_reason(body.reason)
            self.hr.archive_license(id_, body.reason)
            self.session.commit()

        self.run(work)
