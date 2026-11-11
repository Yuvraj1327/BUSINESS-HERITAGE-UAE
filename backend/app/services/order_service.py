"""Customer Order Management (Step 13): customers, orders, status workflow and order payments.
Order revenue and order payments live ONLY in the order tables. They are not posted to daily_reports or to the cash & bank
ledger (no approved relationship; see docs/orders/). The database re-checks the workflow, amounts and branch rules."""

import logging
import uuid
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy.exc import DBAPIError

from app.api.authz import BranchScope, PermissionDeniedError
from app.core import orders as rules
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.core.permissions import Action, Module
from app.repositories.order_repository import OrderFilter, OrderRepository
from app.schemas.orders import (
    Balance,
    CancelIn,
    CategoryOut,
    CustomerFields,
    CustomerIn,
    CustomerOut,
    CustomerPage,
    CustomerUpdate,
    HistoryItem,
    OrderDetail,
    OrderIn,
    OrderPage,
    OrderRow,
    OrderUpdate,
    PaymentIn,
    PaymentOut,
    RefundIn,
    StatusIn,
)
from app.services.base import BaseService
from app.services.finance_core import _message, sqlstate
from app.utils.time import dubai_today

logger = logging.getLogger(__name__)


def order_row(row: dict[str, Any], now0: datetime | None = None) -> OrderRow:
    overdue: Literal["pickup", "delivery"] | None = None
    if now0 is not None:
        if row["status"] in ("New", "Scheduled") and row["pickup_at"] and row["pickup_at"] < now0:
            overdue = "pickup"
        elif row["status"] not in rules.CLOSED and row["delivery_at"] < now0:
            overdue = "delivery"
    keys = OrderRow.model_fields.keys() - {"overdue"}
    return OrderRow(**{k: row[k] for k in keys}, overdue=overdue)


class OrderService(BaseService):
    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.repo = OrderRepository(session)

    # ---- plumbing --------------------------------------------------------------------------------------
    def run(self, fn: Any) -> Any:
        try:
            return fn()
        except DBAPIError as exc:
            self.session.rollback()
            state = sqlstate(exc)
            if state == "42501":
                raise PermissionDeniedError() from exc
            if state == "23505":
                raise ConflictError("That record already exists", code="duplicate") from exc
            if state in ("23514", "23503", "23502"):
                raise UnprocessableError(_message(exc) or "The order breaks a rule") from exc
            logger.warning("unmapped database error %s", state)
            raise
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _now0() -> datetime:
        return rules.day_bounds(dubai_today())[0]

    # ---- categories ------------------------------------------------------------------------------------
    def categories(self) -> list[CategoryOut]:
        return [CategoryOut(**r) for r in self.repo.categories()]

    # ---- customers -------------------------------------------------------------------------------------
    def _customer_visible(self, scope: BranchScope, id_: uuid.UUID) -> dict[str, Any]:
        row = self.repo.customer(id_)  # row-level security hides other branches' customers
        if row is None or not scope.allows(row["branch_id"]):
            raise NotFoundError("Customer not found")
        return row

    def _prepare_customer(self, body: CustomerFields) -> dict[str, Any]:
        v = body.model_dump(exclude={"branch_id"})
        v["mobile"] = rules.normalize_mobile(body.mobile)
        v["whatsapp"] = rules.normalize_mobile(body.whatsapp) if body.whatsapp else None
        return v

    def _new_customer(
        self, scope: BranchScope, branch_id: uuid.UUID, body: CustomerFields
    ) -> uuid.UUID:
        v = self._prepare_customer(body)
        dup = self.repo.customer_by_mobile(branch_id, v["mobile"])
        if dup:
            raise ConflictError(
                f"This mobile number already belongs to {dup['name']}. Select that customer instead.",
                code="duplicate_customer",
                fields={"customer_id": [str(dup["id"])]},
            )
        return self.repo.insert_customer({**v, "branch_id": branch_id})

    def _customer_branch(self, scope: BranchScope, requested: uuid.UUID | None) -> uuid.UUID:
        branch = scope.resolve(requested)
        if branch is None:
            raise UnprocessableError("Choose a branch", fields={"branch_id": ["Choose a branch"]})
        if (b := self.repo.branch(branch)) is None or not b["is_active"]:
            raise UnprocessableError(
                "That branch is not available", fields={"branch_id": ["Choose an active branch"]}
            )
        return branch

    def create_customer(self, scope: BranchScope, body: CustomerIn) -> CustomerOut:
        def work() -> uuid.UUID:
            branch = self._customer_branch(scope, body.branch_id)
            new_id = self._new_customer(scope, branch, body)
            self.session.commit()
            return new_id

        return self.get_customer(scope, self.run(work))

    def get_customer(self, scope: BranchScope, id_: uuid.UUID) -> CustomerOut:
        return CustomerOut(**self._customer_visible(scope, id_))

    def update_customer(
        self, scope: BranchScope, id_: uuid.UUID, body: CustomerUpdate
    ) -> CustomerOut:
        def work() -> None:
            self._customer_visible(scope, id_)
            v = self._prepare_customer(body)
            other = self.repo.customer_by_mobile(
                self._customer_visible(scope, id_)["branch_id"], v["mobile"]
            )
            if other and other["id"] != id_:
                raise ConflictError(
                    f"This mobile number already belongs to {other['name']}.",
                    code="duplicate_customer",
                    fields={"customer_id": [str(other["id"])]},
                )
            self.repo.update_customer(id_, v)
            self.session.commit()

        self.run(work)
        return self.get_customer(scope, id_)

    def list_customers(
        self,
        scope: BranchScope,
        branch_id: uuid.UUID | None,
        q: str | None,
        page: int,
        page_size: int,
    ) -> CustomerPage:
        branch = scope.resolve(branch_id)
        rows, total = self.repo.list_customers(branch, q, page_size, (page - 1) * page_size)
        return CustomerPage(
            items=[CustomerOut(**r) for r in rows], total=total, page=page, page_size=page_size
        )

    # ---- orders ----------------------------------------------------------------------------------------
    def _schedule(self, body: Any) -> tuple[datetime | None, datetime]:
        pickup = (
            rules.to_dubai_datetime(body.pickup_date, body.pickup_time)
            if body.pickup_date and body.pickup_time
            else None
        )
        return pickup, rules.to_dubai_datetime(body.delivery_date, body.delivery_time)

    def _check_category(self, category_id: uuid.UUID) -> None:
        cat = self.repo.category(category_id)
        if cat is None or not cat["is_active"]:
            raise UnprocessableError(
                "Choose an available service category", fields={"category_id": ["Not available"]}
            )

    def create(self, scope: BranchScope, body: OrderIn) -> OrderDetail:
        if body.client_key and (prev := self.repo.order_id_by_key(body.client_key)):
            return self.detail(
                scope, prev
            )  # a repeated submit (double click, retry) returns the same order

        def work() -> uuid.UUID:
            if body.customer_id:
                cust = self._customer_visible(scope, body.customer_id)
                if body.branch_id and body.branch_id != cust["branch_id"]:
                    raise UnprocessableError(
                        "The customer belongs to another branch",
                        fields={"branch_id": ["Does not match the customer"]},
                    )
                branch = scope.ensure(cust["branch_id"])
                customer_id = body.customer_id
            else:
                assert body.new_customer is not None
                branch = self._customer_branch(scope, body.branch_id)
                customer_id = self._new_customer(scope, branch, body.new_customer)
            self._check_category(body.category_id)
            today = dubai_today()
            order_date = body.order_date or today
            if order_date > today:
                raise UnprocessableError(
                    "The order date cannot be in the future", fields={"order_date": ["Future date"]}
                )
            pickup_at, delivery_at = self._schedule(body)
            v = body.model_dump(
                include={"category_id", "service_type", "notes", "pickup_address", "delivery_address",
                         "order_total", "discount", "service_fee"}
            )  # fmt: skip
            order_id = self.repo.insert_order(
                {
                    **v,
                    "customer_id": customer_id,
                    "branch_id": branch,
                    "order_date": order_date,
                    "pickup_at": pickup_at,
                    "delivery_at": delivery_at,
                    "client_key": body.client_key,
                }  # fmt: skip
            )
            if body.initial_payment:
                p = body.initial_payment
                final = rules.final_payable(body.order_total, body.discount, body.service_fee)
                if p.amount > final:
                    raise UnprocessableError(
                        "The amount collected is more than the final payable amount",
                        fields={"initial_payment": ["More than the final payable amount"]},
                    )
                self.repo.insert_payment(
                    {
                        "order_id": order_id,
                        "payment_date": order_date,
                        "amount": p.amount,
                        "method": p.method,
                        "reference": p.reference,
                        "note": "Collected when the order was placed",
                        "client_key": None,
                    }  # fmt: skip
                )
            self.session.commit()
            return order_id

        return self.detail(scope, self.run(work))

    def _load(self, scope: BranchScope, id_: uuid.UUID, for_update: bool = False) -> dict[str, Any]:
        row = self.repo.order_full(
            id_, for_update
        )  # RLS: other branches' orders do not exist for a branch user
        if row is None or not scope.allows(row["branch_id"]):
            raise NotFoundError("Order not found")
        return row

    def detail(self, scope: BranchScope, id_: uuid.UUID) -> OrderDetail:
        full = self._load(scope, id_)
        head = self.repo.order_row(id_)
        assert head is not None
        p = scope.principal
        status = full["status"]
        outstanding = rules.outstanding(full["final_payable"], full["amount_collected"])
        return OrderDetail(
            order=order_row(head, self._now0()),
            category_id=full["category_id"],
            notes=full["notes"],
            order_total=full["order_total"],
            discount=full["discount"],
            service_fee=full["service_fee"],
            cancel_reason=full["cancel_reason"],
            cancelled_at=full["cancelled_at"],
            delivered_at=full["delivered_at"],
            customer_whatsapp=full["customer_whatsapp"],
            customer_address=full["customer_address"],
            created_at=full["created_at"],
            created_by_name=full["created_by_name"],
            updated_at=full["updated_at"],
            updated_by_name=full["updated_by_name"],
            payments=[PaymentOut(**r) for r in self.repo.payments(id_)],
            history=[HistoryItem(**r) for r in self.repo.history(id_)],
            next_status=rules.next_status(status),
            can_edit=status not in rules.CLOSED and p.can(Module.ORDERS, Action.UPDATE),
            can_cancel=status in rules.CANCELLABLE and p.can(Module.ORDERS, Action.MANAGE),
            can_pay=status != "Cancelled"
            and outstanding > 0
            and p.can(Module.ORDER_PAYMENTS, Action.CREATE),
        )

    def update(self, scope: BranchScope, id_: uuid.UUID, body: OrderUpdate) -> OrderDetail:
        def work() -> None:
            row = self._load(scope, id_, for_update=True)
            if row["status"] in rules.CLOSED:
                raise ConflictError(
                    f"A {row['status'].lower()} order can no longer be edited", code="order_locked"
                )
            self._check_category(body.category_id)
            final = rules.final_payable(body.order_total, body.discount, body.service_fee)
            if final < row["amount_collected"]:
                raise UnprocessableError(
                    "The final payable amount cannot be less than the amount already collected",
                    fields={"order_total": ["Less than the amount collected"]},
                )
            pickup_at, delivery_at = self._schedule(body)
            v = body.model_dump(
                include={"category_id", "service_type", "notes", "pickup_address", "delivery_address",
                         "order_total", "discount", "service_fee"}
            )  # fmt: skip
            self.repo.set_reason(body.reason)
            self.repo.update_order(id_, {**v, "pickup_at": pickup_at, "delivery_at": delivery_at})
            self.session.commit()

        self.run(work)
        return self.detail(scope, id_)

    def set_status(self, scope: BranchScope, id_: uuid.UUID, body: StatusIn) -> OrderDetail:
        def work() -> None:
            row = self._load(scope, id_, for_update=True)
            if body.status == "Cancelled":
                raise ConflictError(
                    "Use the cancel action, which needs a reason", code="use_cancel"
                )
            expected = rules.next_status(row["status"])
            if body.status != expected:
                hint = (
                    f"the next step is {expected}" if expected else "it can no longer change status"
                )
                raise ConflictError(
                    f"An order cannot move from {row['status']} to {body.status}; {hint}",
                    code="invalid_transition",
                )
            self.repo.set_reason(None, body.note)
            self.repo.set_status(id_, body.status)
            self.session.commit()

        self.run(work)
        return self.detail(scope, id_)

    def cancel(self, scope: BranchScope, id_: uuid.UUID, body: CancelIn) -> OrderDetail:
        def work() -> None:
            row = self._load(scope, id_, for_update=True)
            if row["status"] not in rules.CANCELLABLE:
                raise ConflictError(
                    f"A {row['status'].lower()} order cannot be cancelled",
                    code="invalid_transition",
                )
            self.repo.set_reason(body.reason)
            self.repo.set_status(id_, "Cancelled", body.reason)
            self.session.commit()

        self.run(work)
        return self.detail(scope, id_)

    def history(self, scope: BranchScope, id_: uuid.UUID) -> list[HistoryItem]:
        self._load(scope, id_)
        return [HistoryItem(**r) for r in self.repo.history(id_)]

    def list_orders(
        self, scope: BranchScope, f: OrderFilter, sort: str, desc: bool, page: int, page_size: int
    ) -> OrderPage:
        branch = scope.resolve(f.branch_id)
        f = OrderFilter(**{**f.__dict__, "branch_id": branch})
        rows, total = self.repo.list_orders(f, sort, desc, page_size, (page - 1) * page_size)
        now0 = self._now0()
        return OrderPage(
            items=[order_row(r, now0) for r in rows], total=total, page=page, page_size=page_size
        )

    def customer_orders(
        self, scope: BranchScope, customer_id: uuid.UUID, page: int, page_size: int
    ) -> OrderPage:
        self._customer_visible(scope, customer_id)
        f = OrderFilter(customer_id=customer_id)
        rows, total = self.repo.list_orders(
            f, "order_date", True, page_size, (page - 1) * page_size
        )
        now0 = self._now0()
        return OrderPage(
            items=[order_row(r, now0) for r in rows], total=total, page=page, page_size=page_size
        )

    # ---- payments --------------------------------------------------------------------------------------
    def payments(self, scope: BranchScope, id_: uuid.UUID) -> list[PaymentOut]:
        self._load(scope, id_)
        return [PaymentOut(**r) for r in self.repo.payments(id_)]

    def balance(self, scope: BranchScope, id_: uuid.UUID) -> Balance:
        row = self._load(scope, id_)
        return Balance(
            order_id=id_,
            final_payable=row["final_payable"],
            amount_collected=row["amount_collected"],
            outstanding=rules.outstanding(row["final_payable"], row["amount_collected"]),
            payment_status=row["payment_status"],
        )

    def add_payment(self, scope: BranchScope, id_: uuid.UUID, body: PaymentIn) -> Balance:
        def work() -> None:
            if body.client_key and (prev := self.repo.payment_by_key(body.client_key)):
                if prev["order_id"] != id_:
                    raise ConflictError(
                        "This payment key was used for another order", code="duplicate"
                    )
                return  # the same submit again: nothing is posted twice
            row = self._load(scope, id_, for_update=True)
            if row["status"] == "Cancelled":
                raise ConflictError(
                    "A cancelled order cannot take payments", code="order_cancelled"
                )
            due = rules.outstanding(row["final_payable"], row["amount_collected"])
            if body.amount > due:
                raise UnprocessableError(
                    f"The payment is more than the outstanding balance (AED {due:.2f})",
                    fields={"amount": [f"At most AED {due:.2f}"]},
                )
            today = dubai_today()
            if body.payment_date and (
                body.payment_date > today or body.payment_date < row["order_date"]
            ):
                raise UnprocessableError(
                    "The payment date must be between the order date and today",
                    fields={"payment_date": ["Out of range"]},
                )
            self.repo.insert_payment(
                {
                    "order_id": id_,
                    "payment_date": body.payment_date,
                    "amount": body.amount,
                    "method": body.method,
                    "reference": body.reference,
                    "note": body.note,
                    "client_key": body.client_key,
                }  # fmt: skip
            )
            self.session.commit()

        self.run(work)
        return self.balance(scope, id_)

    def refund(self, scope: BranchScope, id_: uuid.UUID, body: RefundIn) -> None:
        """No refund workflow has been approved, so nothing is ever refunded or deleted silently."""
        self._load(scope, id_)
        raise ConflictError(
            "Refunds are not enabled: the refund workflow has not been approved by the business",
            code="refund_not_approved",
        )

    def payment_summary(
        self, scope: BranchScope, branch_id: uuid.UUID | None, d_from: date, d_to: date
    ) -> dict[str, Any]:
        branch = scope.resolve(branch_id)
        rows = self.repo.payment_summary(branch, d_from, d_to)
        return {
            "date_from": d_from,
            "date_to": d_to,
            "total": sum((r["total"] for r in rows), start=0),
            "by_method": {
                m: next((r["total"] for r in rows if r["method"] == m), 0)
                for m in rules.PAYMENT_METHODS
            },
            "payment_count": sum(int(r["n"]) for r in rows),
        }
