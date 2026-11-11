import uuid
from datetime import date, timedelta
from typing import Any

from app.core.calculations import ZERO, closing_balance, money
from app.core.exceptions import NotFoundError, UnprocessableError
from app.schemas.finance import (
    AccountsReport,
    AccountSummary,
    Balances,
    BranchCashReport,
    BranchCashRow,
    LedgerPage,
    LedgerRow,
    PosSettlementIn,
    PosSettlementOut,
    TransferIn,
    TransferOut,
)
from app.services.finance_core import FinanceCore
from app.utils.time import dubai_today

ACCOUNTS = ("Cash", "ENBD", "ADCB", "POS Pending")
_COL = {"Cash": "cash_now", "ENBD": "enbd_now", "ADCB": "adcb_now", "POS Pending": "pos_pending"}
MAX_RANGE_DAYS = 366


class CashBankService(FinanceCore):
    # ---- reads -------------------------------------------------------------------------------------------
    def summary(self, as_of: date | None = None) -> Balances:
        today = dubai_today()
        as_of = as_of or today
        if as_of > today:
            raise UnprocessableError(
                "Date cannot be in the future",
                fields={"as_of": ["Date cannot be after today (Dubai)"]},
            )
        if self.tracking_start() is None:
            return Balances(
                status="not_configured",
                tracking_start=None,
                balance_date=None,
                cash_in_hand=None,
                enbd=None,
                adcb=None,
                pos_pending=None,
                total_cash_bank=None,
                total_savings=None,
            )
        b = self.fin.balances(as_of)
        return Balances(
            status="ok",
            tracking_start=b["tracking_start"],
            balance_date=b["balance_date"],
            cash_in_hand=money(b["cash_now"]),
            enbd=money(b["enbd_now"]),
            adcb=money(b["adcb_now"]),
            pos_pending=money(b["pos_pending"]),
            total_cash_bank=money(b["total_cash_bank"]),
            total_savings=money(b["savings_total"]),
        )

    def _range(self, d_from: date | None, d_to: date | None, start: date) -> tuple[date, date]:
        today = dubai_today()
        d_to = d_to or today
        d_from = d_from or max(start, d_to - timedelta(days=29))
        if d_from > d_to:
            raise UnprocessableError(
                "Start date is after end date",
                fields={"date_from": ["Start date must not be after end date"]},
            )
        if d_to > today:
            raise UnprocessableError(
                "End date cannot be in the future",
                fields={"date_to": ["End date cannot be after today (Dubai)"]},
            )
        if (d_to - d_from).days + 1 > MAX_RANGE_DAYS:
            raise UnprocessableError(
                f"Choose at most {MAX_RANGE_DAYS} days",
                fields={"date_from": [f"Choose at most {MAX_RANGE_DAYS} days"]},
            )
        return d_from, d_to

    def accounts(self, d_from: date | None, d_to: date | None) -> AccountsReport:
        today = dubai_today()
        start = self.tracking_start()
        if start is None:
            return AccountsReport(
                status="not_configured",
                date_from=d_from or today,
                date_to=d_to or today,
                accounts=[],
            )
        f, t = self._range(d_from, d_to, start)
        opening = self.fin.balances(f - timedelta(days=1))
        closing = self.fin.balances(t)
        flows = self.fin.ledger_totals(f, t)
        out: list[AccountSummary] = []
        for acc in ACCOUNTS:
            inc = money(flows.get(acc, {}).get("incoming", ZERO))
            outg = money(flows.get(acc, {}).get("outgoing", ZERO))
            out.append(
                AccountSummary(
                    account=acc,  # type: ignore[arg-type]
                    opening=money(opening[_COL[acc]]),
                    incoming=inc,
                    outgoing=outg,
                    closing=money(closing[_COL[acc]]),
                )
            )
            assert closing_balance(money(opening[_COL[acc]]), inc, outg) == money(
                closing[_COL[acc]]
            )
        return AccountsReport(status="ok", date_from=f, date_to=t, accounts=out)

    def branches(self, as_of: date | None = None) -> BranchCashReport:
        today = dubai_today()
        as_of = as_of or today
        if as_of > today:
            raise UnprocessableError(
                "Date cannot be in the future",
                fields={"as_of": ["Date cannot be after today (Dubai)"]},
            )
        if self.tracking_start() is None:
            return BranchCashReport(status="not_configured", balance_date=None, rows=[], total=ZERO)
        rows = [
            BranchCashRow(
                **{
                    k: r[k]
                    for k in (
                        "branch_id",
                        "branch_name",
                        "opening",
                        "incoming",
                        "outgoing",
                        "closing",
                    )
                }
            )
            for r in self.fin.branch_cash(as_of)
        ]
        return BranchCashReport(
            status="ok",
            balance_date=as_of,
            rows=rows,
            total=money(sum((r.closing for r in rows), ZERO)),
        )

    def transactions(
        self,
        d_from: date | None,
        d_to: date | None,
        account: str | None,
        branch: uuid.UUID | None,
        txn_type: str | None,
        page: int,
        page_size: int,
    ) -> LedgerPage:
        start = self.tracking_start()
        if start is None:
            return LedgerPage(
                status="not_configured",
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_incoming=ZERO,
                total_outgoing=ZERO,
            )
        f, t = self._range(d_from, d_to, start)
        rows, total, agg = self.fin.ledger_page(
            f, t, account, branch, txn_type, page_size, (page - 1) * page_size
        )
        return LedgerPage(
            status="ok",
            items=[LedgerRow(**r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_incoming=money(agg["inc"]),
            total_outgoing=money(agg["outg"]),
        )

    def transfers(self) -> list[TransferOut]:
        return [_transfer_out(r) for r in self.fin.transfers()]

    def settlements(self) -> list[PosSettlementOut]:
        return [_settlement_out(r) for r in self.fin.settlements()]

    # ---- writes ------------------------------------------------------------------------------------------
    def create_transfer(self, body: TransferIn) -> TransferOut:
        cash_side = "Cash" in (body.from_account, body.to_account)
        if body.from_account == body.to_account:
            raise UnprocessableError(
                "Choose two different accounts",
                fields={"to_account": ["Must differ from the source account"]},
            )
        if cash_side and body.branch_id is None:
            raise UnprocessableError(
                "Select the branch whose cash is involved",
                fields={"branch_id": ["Select a branch"]},
            )
        if not cash_side and body.branch_id is not None:
            raise UnprocessableError(
                "A bank-to-bank transfer has no branch",
                fields={"branch_id": ["Not used for bank-to-bank transfers"]},
            )

        def work() -> uuid.UUID:
            self.fin.lock()
            d = self.resolve_date(body.transfer_date, "transfer_date")
            if body.branch_id is not None:
                br = self.fin.branch(body.branch_id)
                if br is None or not br["is_active"]:
                    raise UnprocessableError(
                        "Unknown or inactive branch",
                        fields={"branch_id": ["Select an active branch"]},
                    )
            self.ensure_funds(
                body.from_account,
                body.amount,
                d,
                branch=body.branch_id,
                branch_only=body.from_account == "Cash",
            )
            new_id = self.fin.insert_transfer(
                {
                    "transfer_date": d,
                    "from_account": body.from_account,
                    "to_account": body.to_account,
                    "branch_id": body.branch_id,
                    "amount": body.amount,
                    "reference": body.reference,
                    "note": body.note,
                    "client_key": body.client_key,
                }
            )
            self.session.commit()
            return new_id

        new_id = self.run(work)
        return self._transfer(new_id)

    def void_transfer(self, id_: uuid.UUID, reason: str) -> None:
        def work() -> None:
            self.fin.lock()
            row = self.fin.transfer(id_)
            if row is None:
                raise NotFoundError("Transfer not found")
            self.fin.void_ledger("void_cash_transfer", id_, reason)
            self.ensure_no_negative_balances((row["branch_id"],) if row["branch_id"] else ())
            self.session.commit()

        self.run(work)

    def create_settlement(self, body: PosSettlementIn) -> PosSettlementOut:
        def work() -> uuid.UUID:
            self.fin.lock()
            d = self.resolve_date(body.settlement_date, "settlement_date")
            self.ensure_funds("POS Pending", body.amount, d)
            new_id = self.fin.insert_settlement(
                {
                    "settlement_date": d,
                    "bank": body.bank,
                    "amount": body.amount,
                    "reference": body.reference,
                    "note": body.note,
                    "client_key": body.client_key,
                }
            )
            self.session.commit()
            return new_id

        new_id = self.run(work)
        row = self.fin.settlement(new_id)
        assert row is not None
        return _settlement_out(row)

    def void_settlement(self, id_: uuid.UUID, reason: str) -> None:
        def work() -> None:
            self.fin.lock()
            if self.fin.settlement(id_) is None:
                raise NotFoundError("POS settlement not found")
            self.fin.void_ledger("void_pos_settlement", id_, reason)
            self.ensure_no_negative_balances()
            self.session.commit()

        self.run(work)

    def _transfer(self, id_: uuid.UUID) -> TransferOut:
        row = self.fin.transfer(id_)
        assert row is not None
        return _transfer_out(row)


def _transfer_out(r: dict[str, Any]) -> TransferOut:
    return TransferOut(
        id=r["id"],
        transfer_date=r["transfer_date"],
        from_account=r["from_account"],
        to_account=r["to_account"],
        branch_id=r["branch_id"],
        branch_name=r["branch_name"],
        amount=r["amount"],
        reference=r["reference"],
        note=r["note"],
        created_at=r["created_at"],
        voided=r["voided_at"] is not None,
    )


def _settlement_out(r: dict[str, Any]) -> PosSettlementOut:
    return PosSettlementOut(
        id=r["id"],
        settlement_date=r["settlement_date"],
        bank=r["bank"],
        amount=r["amount"],
        reference=r["reference"],
        note=r["note"],
        created_at=r["created_at"],
        voided=r["voided_at"] is not None,
    )
