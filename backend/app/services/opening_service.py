from datetime import date, timedelta

from app.core.calculations import ZERO
from app.core.exceptions import ConflictError, UnprocessableError
from app.schemas.finance import (
    AuditEntry,
    BranchCashOut,
    OpeningBalancesIn,
    OpeningBalancesOut,
    SupplierOpeningOut,
)
from app.services.finance_core import FinanceCore
from app.utils.time import dubai_today


class OpeningBalanceService(FinanceCore):
    def get(self) -> OpeningBalancesOut:
        ob = self.fin.opening()
        branches = [BranchCashOut(**r) for r in self.fin.opening_branch_cash()]
        suppliers = [SupplierOpeningOut(**r) for r in self.fin.supplier_openings()]
        total_cash = sum((b.amount for b in branches), ZERO)
        total_sup = sum((s.amount for s in suppliers), ZERO)
        if ob is None:
            return OpeningBalancesOut(
                status="not_configured",
                as_of_date=None,
                tracking_start=None,
                receipts_bank=None,
                enbd_balance=ZERO,
                adcb_balance=ZERO,
                pos_pending=ZERO,
                savings_brought_forward=ZERO,
                branch_cash=branches,
                supplier_dues=suppliers,
                total_branch_cash=total_cash,
                total_supplier_dues=total_sup,
                date_locked=False,
                updated_at=None,
                updated_by_name=None,
            )
        return OpeningBalancesOut(
            status="configured",
            as_of_date=ob["as_of_date"],
            tracking_start=ob["as_of_date"] + timedelta(days=1),
            receipts_bank=ob["receipts_bank"],
            enbd_balance=ob["enbd_balance"],
            adcb_balance=ob["adcb_balance"],
            pos_pending=ob["pos_pending"],
            savings_brought_forward=ob["savings_brought_forward"],
            branch_cash=branches,
            supplier_dues=suppliers,
            total_branch_cash=total_cash,
            total_supplier_dues=total_sup,
            date_locked=self.fin.flows_exist(),
            updated_at=ob["updated_at"],
            updated_by_name=ob["updated_by_name"],
        )

    def history(self) -> list[AuditEntry]:
        return [AuditEntry(**r) for r in self.fin.opening_history()]

    def save(self, body: OpeningBalancesIn, today: date | None = None) -> OpeningBalancesOut:
        today = today or dubai_today()
        errors: dict[str, list[str]] = {}
        if body.as_of_date > today:
            errors["as_of_date"] = ["Opening balance date cannot be in the future (Dubai time)"]

        known = {r["branch_id"]: r for r in self.fin.opening_branch_cash()}
        sent = [b.branch_id for b in body.branch_cash]
        if len(set(sent)) != len(sent):
            errors["branch_cash"] = ["Each branch may appear only once"]
        elif set(sent) != set(known):
            errors["branch_cash"] = [
                "Enter an opening cash balance for every one of the configured branches"
            ]
        sup_known = {r["supplier_id"]: r for r in self.fin.supplier_openings()}
        sup_sent = [s.supplier_id for s in body.supplier_dues]
        if len(set(sup_sent)) != len(sup_sent):
            errors["supplier_dues"] = ["Each supplier may appear only once"]
        elif not set(sup_sent) <= set(sup_known):
            errors["supplier_dues"] = ["Unknown supplier"]
        if errors:
            raise UnprocessableError("Opening balances are not valid", fields=errors)

        def work() -> None:
            self.fin.lock()
            existing = self.fin.opening()
            if existing is not None:
                if not body.reason:
                    raise UnprocessableError(
                        "A reason is required to change saved opening balances",
                        fields={"reason": ["Explain why the opening balances are being corrected"]},
                    )
                if existing["as_of_date"] != body.as_of_date and self.fin.flows_exist():
                    raise ConflictError(
                        "The opening balance date cannot change once reports or finance entries exist",
                        code="opening_date_locked",
                        fields={
                            "as_of_date": ["Locked: transactions already exist after this date"]
                        },
                    )
            self.fin.set_reason(body.reason or "Initial opening balances")
            self.fin.upsert_opening(
                body.model_dump(
                    include={
                        "as_of_date",
                        "receipts_bank",
                        "enbd_balance",
                        "adcb_balance",
                        "pos_pending",
                        "savings_brought_forward",
                    }
                )
            )
            for b in body.branch_cash:
                self.fin.upsert_branch_cash(b.branch_id, b.amount)
            for s in body.supplier_dues:
                self.fin.set_supplier_opening(s.supplier_id, s.amount)
            # A correction may never leave an account or supplier negative once transactions are counted.
            self.ensure_no_negative_balances()
            self.session.commit()

        self.run(work)
        return self.get()
