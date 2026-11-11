import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.finance import Strict
from app.schemas.money import Money, MoneyIn, PositiveMoneyIn

ServiceType = Literal["Standard", "Express"]
PaymentMethod = Literal["Cash", "POS", "Bank Transfer", "Payment Link"]
OrderStatus = Literal[
    "New",
    "Scheduled",
    "Picked Up",
    "Processing",
    "Ready",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
]
PaymentStatus = Literal["Unpaid", "Partial", "Paid", "Refunded"]


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


# ---------------------------------------------------------------- customers
class CustomerFields(Strict):
    name: str = Field(min_length=2, max_length=150)
    mobile: str = Field(min_length=5, max_length=30)
    whatsapp: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    area: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Enter the customer's name")
        return v

    @field_validator("whatsapp", "address", "area", "notes")
    @classmethod
    def _opt(cls, v: str | None) -> str | None:
        return _clean(v)


class CustomerIn(CustomerFields):
    branch_id: uuid.UUID | None = (
        None  # branch users: ignored / must equal their branch; owner: required
    )


class CustomerUpdate(CustomerFields):
    pass


class CustomerOut(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    branch_name: str
    name: str
    mobile: str
    whatsapp: str | None
    address: str | None
    area: str | None
    notes: str | None
    order_count: int = 0
    total_billed: Money
    outstanding: Money
    last_order_date: date | None = None
    created_at: datetime


class CustomerPage(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- orders
class InitialPayment(Strict):
    amount: PositiveMoneyIn
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=100)


class OrderFields(Strict):
    category_id: uuid.UUID
    service_type: ServiceType
    notes: str | None = Field(default=None, max_length=2000)
    pickup_date: date | None = None
    pickup_time: time | None = None
    pickup_address: str | None = Field(default=None, max_length=500)
    delivery_date: date
    delivery_time: time
    delivery_address: str | None = Field(default=None, max_length=500)
    order_total: MoneyIn
    discount: MoneyIn = 0  # type: ignore[assignment]
    service_fee: MoneyIn = 0  # type: ignore[assignment]

    @field_validator("notes", "pickup_address", "delivery_address")
    @classmethod
    def _opt(cls, v: str | None) -> str | None:
        return _clean(v)

    @model_validator(mode="after")
    def _rules(self) -> "OrderFields":
        if (self.pickup_date is None) != (self.pickup_time is None):
            raise ValueError("Give both the pickup date and the pickup time, or neither")
        if (
            self.pickup_date
            and self.pickup_time
            and (self.delivery_date, self.delivery_time) < (self.pickup_date, self.pickup_time)
        ):
            raise ValueError("Expected delivery cannot be earlier than the pickup")
        if self.discount > self.order_total + self.service_fee:
            raise ValueError(
                "The discount cannot be more than the order total plus the service fee"
            )
        if self.order_total - self.discount + self.service_fee <= 0:
            raise ValueError("The final payable amount must be more than zero")
        return self


class OrderIn(OrderFields):
    customer_id: uuid.UUID | None = None
    new_customer: CustomerFields | None = None
    branch_id: uuid.UUID | None = None
    order_date: date | None = None
    initial_payment: InitialPayment | None = None
    client_key: uuid.UUID | None = None

    @model_validator(mode="after")
    def _customer(self) -> "OrderIn":
        if (self.customer_id is None) == (self.new_customer is None):
            raise ValueError("Choose an existing customer or enter a new one")
        return self


class OrderUpdate(OrderFields):
    reason: str | None = Field(default=None, max_length=500)


class StatusIn(Strict):
    status: OrderStatus
    note: str | None = Field(default=None, max_length=500)


class CancelIn(Strict):
    reason: str = Field(min_length=3, max_length=500)
    confirm: Literal[True]


class PaymentIn(Strict):
    amount: PositiveMoneyIn
    method: PaymentMethod
    payment_date: date | None = None
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    client_key: uuid.UUID | None = None

    @field_validator("reference", "note")
    @classmethod
    def _opt(cls, v: str | None) -> str | None:
        return _clean(v)


class RefundIn(Strict):
    amount: PositiveMoneyIn
    reason: str = Field(min_length=3, max_length=500)


class PaymentOut(BaseModel):
    id: uuid.UUID
    payment_date: date
    amount: Money
    method: str
    reference: str | None
    note: str | None
    recorded_by: str | None
    created_at: datetime


class OrderRow(BaseModel):
    id: uuid.UUID
    order_no: str
    customer_id: uuid.UUID
    customer_name: str
    mobile: str
    area: str | None
    branch_id: uuid.UUID
    branch_name: str
    category: str
    service_type: str
    status: str
    payment_status: str
    order_date: date
    pickup_at: datetime | None
    pickup_address: str | None
    delivery_at: datetime
    delivery_address: str | None
    final_payable: Money
    amount_collected: Money
    outstanding: Money
    overdue: Literal["pickup", "delivery"] | None = None


class OrderPage(BaseModel):
    items: list[OrderRow]
    total: int
    page: int
    page_size: int


class HistoryItem(BaseModel):
    id: int
    from_status: str | None
    to_status: str
    changed_by: str | None
    changed_at: datetime
    note: str | None


class OrderDetail(BaseModel):
    order: OrderRow
    category_id: uuid.UUID
    notes: str | None
    order_total: Money
    discount: Money
    service_fee: Money
    cancel_reason: str | None
    cancelled_at: datetime | None
    delivered_at: datetime | None
    customer_whatsapp: str | None
    customer_address: str | None
    created_at: datetime
    created_by_name: str | None
    updated_at: datetime
    updated_by_name: str | None
    payments: list[PaymentOut]
    history: list[HistoryItem]
    next_status: str | None
    can_edit: bool
    can_cancel: bool
    can_pay: bool


class Balance(BaseModel):
    order_id: uuid.UUID
    final_payable: Money
    amount_collected: Money
    outstanding: Money
    payment_status: str


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool


# ---------------------------------------------------------------- dashboard / operations
class OrderKpis(BaseModel):
    total_orders: int
    todays_pickups: int
    todays_deliveries: int
    monthly_revenue: Money
    outstanding_payments: Money


class Section(BaseModel):
    key: str
    title: str
    count: int
    items: list[OrderRow]


class OrderDashboard(BaseModel):
    date: date
    kpis: OrderKpis
    sections: list[Section]


class PaymentSummary(BaseModel):
    date_from: date
    date_to: date
    total: Money
    by_method: dict[str, Money]
    payment_count: int
