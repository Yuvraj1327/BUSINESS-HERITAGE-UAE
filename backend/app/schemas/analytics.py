"""Step 12 response models for Reports & Analytics. Every report is one table shape so the screen, the CSV and the
Excel export are produced from the SAME rows (the exported totals can never differ from the screen)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

ColumnKind = Literal["text", "money", "int", "pct", "date", "datetime"]
Period = Literal["day", "week", "month", "year"]


class ReportColumn(BaseModel):
    key: str
    label: str
    kind: ColumnKind = "text"


class SummaryItem(BaseModel):
    label: str
    value: Any
    kind: ColumnKind = "text"


class AppliedFilters(BaseModel):
    date_from: date
    date_to: date
    period: Period
    branch_id: uuid.UUID | None
    branch_name: str
    supplier_id: uuid.UUID | None = None
    account: str | None = None


class ReportOut(BaseModel):
    key: str
    title: str
    description: str
    filters: AppliedFilters
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    summary: list[SummaryItem]
    notes: list[str]
    generated_at: datetime


class ReportCatalogItem(BaseModel):
    key: str
    title: str
    category: str
    description: str


class OverviewKpis(BaseModel):
    total_sales: Any
    total_collections: Any
    total_orders: int
    shop_expenses: Any
    head_office_expenses: Any
    total_savings: Any
    sales_minus_expenses: Any
    cash_bank_balance: Any | None
    not_yet_received: Any
    balance_status: str
    balance_date: date | None


class Overview(BaseModel):
    filters: AppliedFilters
    kpis: OverviewKpis
    notes: list[str]
    generated_at: datetime


class ChartPoint(BaseModel):
    label: str
    values: dict[str, Any]


class Chart(BaseModel):
    key: str
    title: str
    kind: Literal["line", "bar", "pie"]
    unit: Literal["AED", "count"]
    series: list[str]
    points: list[ChartPoint]
    empty_message: str


class ChartSet(BaseModel):
    filters: AppliedFilters
    charts: list[Chart]
    generated_at: datetime
