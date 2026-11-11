"""Step 9 request/response models: employees, leave, visas & passports, trade licenses, compliance alerts."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.finance import AuditEntry, Strict
from app.schemas.money import Money, MoneyIn

EmploymentStatus = Literal["Active", "On Leave", "Visa Cancelled"]
ExpiryStatusT = Literal["expired", "urgent", "upcoming", "normal", "not_recorded", "cancelled"]
LeaveStateT = Literal[
    "not_on_leave", "on_leave", "approaching_limit", "limit_reached", "visa_cancelled"
]

_MIN_DATE, _MAX_DATE = date(2000, 1, 1), date(2100, 12, 31)


def _blank_to_none(v: str | None) -> str | None:
    return v or None


def _sane(v: date | None) -> date | None:
    if v is not None and not (_MIN_DATE <= v <= _MAX_DATE):
        raise ValueError("Enter a realistic date (2000 to 2100)")
    return v


# ---------------------------------------------------------------- employees
class EmployeeIn(Strict):
    full_name: str = Field(min_length=1, max_length=150)
    branch_id: uuid.UUID
    role_title: str | None = Field(default=None, max_length=100)
    monthly_salary: MoneyIn
    passport_expiry: date | None = None
    visa_expiry: date | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("role_title", "notes")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        return _blank_to_none(v)

    @field_validator("passport_expiry", "visa_expiry")
    @classmethod
    def _dates(cls, v: date | None) -> date | None:
        return _sane(v)


class EmployeeUpdate(EmployeeIn):
    # Required (3+ chars) by the service whenever salary, branch, passport or visa expiry change.
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class StatusChangeIn(Strict):
    status: EmploymentStatus
    leave_start: date | None = None  # required for "On Leave"
    return_date: date | None = None  # for "Active" (return to work); default today (Dubai)
    cancellation_date: date | None = None  # for "Visa Cancelled"; default today (Dubai)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("leave_start", "return_date", "cancellation_date")
    @classmethod
    def _dates(cls, v: date | None) -> date | None:
        return _sane(v)


class ReturnIn(Strict):
    return_date: date | None = None
    reason: str = Field(min_length=3, max_length=500)


class LeaveUpdateIn(Strict):
    leave_start: date
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("leave_start")
    @classmethod
    def _dates(cls, v: date) -> date:
        return _sane(v)  # type: ignore[return-value]


class ArchiveIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class LeaveOut(BaseModel):
    leave_start: date
    limit_date: date
    days_on_leave: int
    days_remaining: int
    state: LeaveStateT


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    branch_id: uuid.UUID
    branch_name: str
    role_title: str | None
    monthly_salary: Money
    status: EmploymentStatus  # effective status (a cancelled visa wins over the stored work status)
    stored_status: Literal["Active", "Leave"]
    leave: LeaveOut | None
    visa_cancelled: bool  # permanent flag OR cancelled by the six-month rule
    visa_cancelled_date: date | None
    visa_expiry: date | None
    visa_status: ExpiryStatusT
    visa_days_remaining: int | None
    passport_expiry: date | None
    passport_status: ExpiryStatusT
    passport_days_remaining: int | None
    notes: str | None
    payroll_eligible: bool
    archived: bool
    archive_reason: str | None
    created_at: datetime
    updated_at: datetime
    created_by_name: str | None
    updated_by_name: str | None


class EmployeePage(BaseModel):
    items: list[EmployeeOut]
    total: int
    page: int
    page_size: int


class EmployeeSummary(BaseModel):
    total_active: int
    on_leave: int
    close_to_limit: int
    visa_cancelled: int
    monthly_payroll: Money
    payroll_employees: int


class EmployeeDetail(BaseModel):
    employee: EmployeeOut
    history: list[AuditEntry]


class LeaveSummary(BaseModel):
    on_leave: int
    approaching: int
    limit_reached: int
    visa_cancelled_by_leave: int
    items: list[EmployeeOut]  # approaching, reached or past the limit; most urgent first


# ---------------------------------------------------------------- visas & passports
class ComplianceRow(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    branch_id: uuid.UUID
    branch_name: str
    employment_status: EmploymentStatus
    expiry_date: date | None
    status: ExpiryStatusT
    days_remaining: int | None


class CompliancePage(BaseModel):
    items: list[ComplianceRow]
    total: int
    page: int
    page_size: int


class BucketCounts(BaseModel):
    expired: int
    urgent: int
    upcoming: int
    normal: int
    not_recorded: int
    cancelled: int = 0


class ComplianceSummary(BaseModel):
    visas: BucketCounts
    passports: BucketCounts
    visas_expiring_30: int
    passports_expiring_30: int
    passports_under_6_months: int
    visas_cancelled: int


class ExpiryUpdateIn(Strict):
    expiry_date: date
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("expiry_date")
    @classmethod
    def _dates(cls, v: date) -> date:
        return _sane(v)  # type: ignore[return-value]

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class ExpiryChange(BaseModel):
    occurred_at: datetime
    actor_name: str | None
    old_expiry: date | None
    new_expiry: date | None
    reason: str | None


# ---------------------------------------------------------------- trade licenses
class LicenseIn(Strict):
    branch_id: uuid.UUID
    license_no: str = Field(min_length=1, max_length=100)
    authority: str | None = Field(default=None, max_length=150)
    expiry_date: date
    renewal_fee: MoneyIn
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("authority", "notes")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        return _blank_to_none(v)

    @field_validator("expiry_date")
    @classmethod
    def _dates(cls, v: date) -> date:
        return _sane(v)  # type: ignore[return-value]


class LicenseUpdate(LicenseIn):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class RenewIn(Strict):
    expected_expiry: (
        date  # the expiry the Owner saw and confirmed: a stale or repeated click is refused (409)
    )
    renewal_fee: MoneyIn | None = None  # default: the licence's renewal fee
    note: str | None = Field(default=None, max_length=500)
    client_key: uuid.UUID | None = None

    @field_validator("note")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class LicenseOut(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    branch_name: str
    license_no: str
    authority: str | None
    expiry_date: date
    renewal_fee: Money
    notes: str | None
    status: ExpiryStatusT
    days_remaining: int
    renewal_count: int
    last_renewed_on: date | None
    archived: bool
    created_at: datetime
    updated_at: datetime
    updated_by_name: str | None


class LicensePage(BaseModel):
    items: list[LicenseOut]
    total: int
    page: int
    page_size: int


class LicenseSummary(BaseModel):
    total: int
    expired: int
    expiring_30: int
    expiring_60: int
    renewal_fees_due: Money
    fees_due_count: int


class RenewalOut(BaseModel):
    id: uuid.UUID
    license_id: uuid.UUID
    renewed_on: date
    previous_expiry: date
    new_expiry: date
    renewal_fee: Money
    note: str | None
    created_at: datetime
    created_by_name: str | None


class LicenseDetail(BaseModel):
    license: LicenseOut
    renewals: list[RenewalOut]
    history: list[AuditEntry]


# ---------------------------------------------------------------- alerts
class ComplianceAlert(BaseModel):
    key: str  # one per record + condition, so the same condition is never reported twice
    branch_name: str | None = None
    record_id: str | None = None
    kind: Literal[
        "visa_expired",
        "visa_expiring",
        "passport_expired",
        "passport_expiring",
        "leave_limit_approaching",
        "visa_cancelled_by_leave",
        "license_expired",
        "license_expiring",
        "license_renewal_due",
    ]
    severity: Literal["danger", "warning"]
    title: str
    detail: str
    due_date: date | None
    days_remaining: int | None
    href: str  # in-app link to the employee / licence record


class AlertFeed(BaseModel):
    items: list[ComplianceAlert]
    total: int
    danger: int
    warning: int
