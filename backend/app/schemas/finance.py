"""Step 8 request/response models: opening balances, cash & banks, expenses, suppliers."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.money import Money, MoneyIn, PositiveMoneyIn

Account = Literal["Cash", "ENBD", "ADCB"]
Bank = Literal["ENBD", "ADCB"]
LedgerAccount = Literal["Cash", "ENBD", "ADCB", "POS Pending"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _blank_to_none(v: str | None) -> str | None:
    return v or None


# ---------------------------------------------------------------- opening balances
class BranchCashIn(Strict):
    branch_id: uuid.UUID
    amount: MoneyIn


class SupplierOpeningIn(Strict):
    supplier_id: uuid.UUID
    amount: MoneyIn


class OpeningBalancesIn(Strict):
    as_of_date: date
    receipts_bank: Bank
    enbd_balance: MoneyIn
    adcb_balance: MoneyIn
    pos_pending: MoneyIn
    savings_brought_forward: MoneyIn
    branch_cash: list[BranchCashIn]
    supplier_dues: list[SupplierOpeningIn] = Field(default_factory=list)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class BranchCashOut(BaseModel):
    branch_id: uuid.UUID
    branch_name: str
    amount: Money


class SupplierOpeningOut(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    amount: Money


class OpeningBalancesOut(BaseModel):
    status: Literal["not_configured", "configured"]
    as_of_date: date | None
    tracking_start: date | None
    receipts_bank: Bank | None
    enbd_balance: Money
    adcb_balance: Money
    pos_pending: Money
    savings_brought_forward: Money
    branch_cash: list[BranchCashOut]
    supplier_dues: list[SupplierOpeningOut]
    total_branch_cash: Money
    total_supplier_dues: Money
    date_locked: bool
    updated_at: datetime | None
    updated_by_name: str | None


class AuditEntry(BaseModel):
    id: int
    occurred_at: datetime
    actor_name: str | None
    action: str
    table_name: str
    record_id: str | None
    reason: str | None
    old_values: dict[str, object] | None
    new_values: dict[str, object] | None


# ---------------------------------------------------------------- cash & banks
class Balances(BaseModel):
    status: Literal["not_configured", "ok"]
    tracking_start: date | None
    balance_date: date | None
    cash_in_hand: Money | None
    enbd: Money | None
    adcb: Money | None
    pos_pending: Money | None
    total_cash_bank: Money | None
    total_savings: Money | None


class AccountSummary(BaseModel):
    account: LedgerAccount
    opening: Money
    incoming: Money
    outgoing: Money
    closing: Money


class AccountsReport(BaseModel):
    status: Literal["not_configured", "ok"]
    date_from: date
    date_to: date
    accounts: list[AccountSummary]


class BranchCashRow(BaseModel):
    branch_id: uuid.UUID | None
    branch_name: str
    opening: Money
    incoming: Money
    outgoing: Money
    closing: Money


class BranchCashReport(BaseModel):
    status: Literal["not_configured", "ok"]
    balance_date: date | None
    rows: list[BranchCashRow]
    total: Money


class LedgerRow(BaseModel):
    txn_date: date
    txn_type: str
    source_table: str
    source_id: uuid.UUID
    branch_id: uuid.UUID | None
    branch_name: str | None
    account: LedgerAccount
    amount: Money
    description: str | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    created_at: datetime


class LedgerPage(BaseModel):
    status: Literal["not_configured", "ok"]
    items: list[LedgerRow]
    total: int
    page: int
    page_size: int
    total_incoming: Money
    total_outgoing: Money


class TransferIn(Strict):
    transfer_date: date | None = None
    from_account: Account
    to_account: Account
    branch_id: uuid.UUID | None = None
    amount: PositiveMoneyIn
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    client_key: uuid.UUID | None = None


class PosSettlementIn(Strict):
    settlement_date: date | None = None
    bank: Bank
    amount: PositiveMoneyIn
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    client_key: uuid.UUID | None = None


class TransferOut(BaseModel):
    id: uuid.UUID
    transfer_date: date
    from_account: Account
    to_account: Account
    branch_id: uuid.UUID | None
    branch_name: str | None
    amount: Money
    reference: str | None
    note: str | None
    created_at: datetime
    voided: bool


class PosSettlementOut(BaseModel):
    id: uuid.UUID
    settlement_date: date
    bank: Bank
    amount: Money
    reference: str | None
    note: str | None
    created_at: datetime
    voided: bool


class VoidIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------- expenses
class ExpenseCategoryOut(BaseModel):
    id: uuid.UUID
    name: str


class ExpenseIn(Strict):
    expense_date: date | None = None
    branch_id: uuid.UUID | None = None  # None = All branches
    category_id: uuid.UUID
    amount: PositiveMoneyIn
    paid_from: Account
    note: str | None = Field(default=None, max_length=500)
    is_saving: bool = False
    client_key: uuid.UUID | None = None


class ExpenseCorrectionIn(ExpenseIn):
    reason: str = Field(min_length=3, max_length=500)


class SavingIn(Strict):
    is_saving: bool
    reason: str = Field(min_length=3, max_length=500)


class ExpenseOut(BaseModel):
    id: uuid.UUID
    expense_date: date
    branch_id: uuid.UUID | None
    branch_name: str | None
    category_id: uuid.UUID
    category: str
    amount: Money
    paid_from: Account
    note: str | None
    is_saving: bool
    voided: bool
    void_reason: str | None
    corrects_id: uuid.UUID | None
    created_at: datetime
    created_by_name: str | None


class ExpenseTotals(BaseModel):
    total: Money
    savings: Money
    excl_savings: Money
    count: int


class ExpensePage(BaseModel):
    items: list[ExpenseOut]
    total: int
    page: int
    page_size: int
    totals: ExpenseTotals


class ExpenseDetail(BaseModel):
    expense: ExpenseOut
    history: list[AuditEntry]


# ---------------------------------------------------------------- suppliers
class SupplierIn(Strict):
    name: str = Field(min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=200)  # "Supplies / service description"
    payment_terms: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    is_active: bool = True
    opening_outstanding: MoneyIn | None = (
        None  # only accepted before opening balances are configured
    )

    @field_validator("category", "payment_terms", "notes")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class SupplierUpdate(Strict):
    name: str = Field(min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=200)
    payment_terms: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    is_active: bool

    @field_validator("category", "payment_terms", "notes")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class SupplierOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None
    payment_terms: str | None
    notes: str | None
    is_active: bool
    opening_outstanding: Money
    new_dues: Money
    total_paid: Money
    outstanding: Money
    created_at: datetime


class SupplierPage(BaseModel):
    items: list[SupplierOut]
    total: int
    page: int
    page_size: int


class SupplierSummary(BaseModel):
    total_suppliers: int
    total_outstanding: Money
    total_paid: Money
    with_outstanding: int


class SupplierPaymentIn(Strict):
    payment_date: date | None = None
    amount: PositiveMoneyIn
    paid_from: Account
    branch_id: uuid.UUID | None = None  # optional: which branch's cash paid (cash payments only)
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    client_key: uuid.UUID | None = None


class MarkPaidIn(Strict):
    payment_date: date | None = None
    paid_from: Account
    branch_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    client_key: uuid.UUID | None = None


class SupplierDueIn(Strict):
    entry_date: date | None = None
    amount: PositiveMoneyIn
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    client_key: uuid.UUID | None = None


class SupplierEntryOut(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    entry_date: date
    kind: Literal["due", "payment"]
    amount: Money
    paid_from: Account | None
    branch_name: str | None
    reference: str | None
    note: str | None
    voided: bool
    void_reason: str | None
    created_at: datetime
    created_by_name: str | None


class SupplierEntryPage(BaseModel):
    items: list[SupplierEntryOut]
    total: int
    page: int
    page_size: int
