import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.money import Money, MoneyIn


class DailyReportCreate(BaseModel):
    """Body of POST /daily-reports. Structural and arithmetic rules live here; the Dubai-time future-date rule and
    branch authorization are applied by the service. Unknown fields are rejected, so a `created_by` or `role` smuggled
    into the body is an error, never silently used."""

    model_config = ConfigDict(extra="forbid")

    report_date: date | None = Field(None, description="Defaults to today in Asia/Dubai")
    branch_id: uuid.UUID | None = Field(
        None, description="Owner: required. Branch user: omit, or own branch only"
    )
    total_sales: MoneyIn
    order_count: int = Field(0, ge=0, le=1_000_000)
    cash_received: MoneyIn = Decimal(0)
    pos_amount: MoneyIn = Decimal(0)
    bank_transfer: MoneyIn = Decimal(0)
    link_payment: MoneyIn = Decimal(0)
    shop_expenses: MoneyIn = Decimal(0)
    shop_savings: MoneyIn = Decimal(0)

    @model_validator(mode="after")
    def _rules(self) -> "DailyReportCreate":
        if self.total_sales <= 0:
            raise ValueError("Total sales must be greater than zero")
        if self.shop_savings > self.shop_expenses:
            raise ValueError("Savings cannot exceed shop expenses")
        return self


class DailyReportOut(BaseModel):
    id: uuid.UUID
    report_date: date
    branch_id: uuid.UUID
    branch_name: str
    total_sales: Money
    order_count: int
    cash_received: Money
    pos_amount: Money
    bank_transfer: Money
    link_payment: Money
    shop_expenses: Money
    shop_savings: Money
    # Computed by app.core.calculations, never by the client
    total_received: Money
    difference: Money
    check: Literal["Matches", "Diff"]
    shop_expenses_excl_savings: Money
    created_at: datetime


class DailyReportPage(BaseModel):
    items: list[DailyReportOut]
    total: int
    page: int
    page_size: int


class VoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
