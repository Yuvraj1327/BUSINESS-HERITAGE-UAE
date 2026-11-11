"""Step 13 API tests: customers, orders, status workflow, payments, pickup & delivery operations, dashboard, order reports and
exports, branch isolation and separation from the finance modules. Own disposable database (migrations 0001-0017).
Real FastAPI app + PostgreSQL + RLS as the restricted `app_api` role."""

import csv
import io
import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.security import TokenVerifier
from app.main import create_app
from app.utils.time import dubai_today
from tests.conftest import _ROOT, APP_API_PASSWORD, make_settings
from tests.jwt_helpers import FakeJwks, KeyPair, claims

pytestmark = pytest.mark.integration
API = "/api/v1"
TODAY = dubai_today()
OPEN_AS_OF = TODAY - timedelta(days=9)


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def t11_dsn(pg_admin_dsn: str) -> Iterator[str]:
    name = f"alsafa_t13_{uuid.uuid4().hex[:8]}"
    base = pg_admin_dsn.rsplit("dbname=", 1)[0]
    with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    dsn = f"{base}dbname={name}"
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((_ROOT / "tests" / "stub_supabase.sql").read_text())
            for m in sorted((_ROOT / "migrations").glob("*.sql")):
                c.execute(m.read_text())
        yield dsn
    finally:
        with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture(scope="module")
def app_url(t11_dsn: str) -> str:
    name = t11_dsn.rsplit("dbname=", 1)[1]
    return f"postgresql://app_api:{APP_API_PASSWORD}@/{name}?host=/tmp&port=54329"


@pytest.fixture(scope="module")
def key() -> KeyPair:
    return KeyPair("kid-step13")


@pytest.fixture(scope="module")
def admin(t11_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(t11_dsn, autocommit=True) as c:
        yield c


@pytest.fixture(scope="module")
def bid(admin) -> dict[str, uuid.UUID]:
    return {n: i for i, n in admin.execute("select id, name from public.branches")}


def _user(admin, role: str, branch: uuid.UUID | None) -> uuid.UUID:
    uid = uuid.uuid4()
    admin.execute(
        "insert into auth.users (id, email) values (%s,%s)", (uid, f"{uid.hex[:10]}@example.test")
    )
    admin.execute(
        "insert into public.profiles (user_id, full_name, role, branch_id, is_active) values (%s,%s,%s,%s,true)",
        (uid, f"{role} test", role, branch),
    )
    return uid


@pytest.fixture(scope="module")
def owner(admin) -> uuid.UUID:
    return _user(admin, "owner", None)


@pytest.fixture(scope="module")
def branch_user(admin, bid) -> uuid.UUID:
    return _user(admin, "branch", bid["ALSAFA MAIN"])


@pytest.fixture(scope="module")
def other_user(admin, bid) -> uuid.UUID:
    return _user(admin, "branch", bid["JERNAS"])


@pytest.fixture(autouse=True)
def wipe(admin) -> Iterator[None]:
    admin.execute(
        "truncate public.order_payments, public.order_status_history, public.orders, public.customers cascade"
    )
    for t in (
        "employees",
        "trade_licenses",
        "supplier_entries",
        "suppliers",
        "pos_settlements",
        "cash_transfers",
        "head_office_expenses",
        "daily_reports",
        "opening_branch_cash",
        "opening_balances",
    ):
        admin.execute(f"delete from public.{t}")
    yield


@pytest.fixture()
def client(app_url: str, key: KeyPair) -> Iterator[TestClient]:
    settings = make_settings(supabase_url="https://abcd.supabase.test", database_url=app_url)
    app = create_app(settings)
    app.state.token_verifier = TokenVerifier(settings, fetcher=FakeJwks(key))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class Api:
    def __init__(
        self,
        client: TestClient,
        key: KeyPair,
        owner: uuid.UUID,
        branch: uuid.UUID,
        other: uuid.UUID,
    ) -> None:
        self.c, self.k, self.o, self.b, self.x = client, key, owner, branch, other

    def h(self, who: str = "owner") -> dict[str, str]:
        uid = {"owner": self.o, "branch": self.b, "other": self.x}[who]
        return {"Authorization": f"Bearer {self.k.sign(claims(uid))}"}

    def get(self, path: str, who: str = "owner", **params):
        return self.c.get(f"{API}{path}", params=params, headers=self.h(who))

    def post(self, path: str, body: dict | None = None, who: str = "owner"):
        return self.c.post(f"{API}{path}", json=body or {}, headers=self.h(who))

    def put(self, path: str, body: dict, who: str = "owner"):
        return self.c.put(f"{API}{path}", json=body, headers=self.h(who))

    def patch(self, path: str, body: dict, who: str = "owner"):
        return self.c.patch(f"{API}{path}", json=body, headers=self.h(who))

    def arch(self, path: str, body: dict, who: str = "owner"):
        return self.post(path, body, who)


@pytest.fixture()
def api(client, key, owner, branch_user, other_user) -> Api:
    return Api(client, key, owner, branch_user, other_user)


# ---------------------------------------------------------------- helpers
D = timedelta


def iso(d) -> str:
    return d.isoformat()


def code(r) -> str:
    return r.json()["error"]["code"]


def dec(v) -> Decimal:
    return Decimal(str(v))


MAIN: dict[str, uuid.UUID] = {}


@pytest.fixture(autouse=True)
def _main_branch(bid) -> None:
    MAIN["id"] = bid["ALSAFA MAIN"]


@pytest.fixture()
def cat(admin) -> str:
    return str(
        admin.execute(
            "select id from public.service_categories where name='Wash & Iron'"
        ).fetchone()[0]
    )


def new_cust(name="Aisha Khan", mobile="0501234567", **over) -> dict:
    return {"name": name, "mobile": mobile, "address": "Villa 4, Al Satwa", "area": "Satwa", **over}


def body(cat, **over) -> dict:
    b = {
        "category_id": cat, "service_type": "Standard",
        "pickup_date": iso(TODAY), "pickup_time": "10:00",
        "pickup_address": "Villa 4, Al Satwa",
        "delivery_date": iso(TODAY + D(days=2)), "delivery_time": "18:00",
        "delivery_address": "Villa 4, Al Satwa",
        "order_total": "100.00", "discount": "0", "service_fee": "0",
    }  # fmt: skip
    b.update(over)
    return b


def place(api, cat, who="owner", branch=None, **over) -> dict:
    """Create an order with a new customer (unique mobile per call) and return the detail."""
    n = uuid.uuid4().int % 10**8
    b = body(cat, **over)
    if "customer_id" not in b:
        b.setdefault("new_customer", new_cust(name=f"Customer {n}", mobile=f"05{n:08d}"))
    if branch is not None:
        b["branch_id"] = str(branch)
    elif who == "owner" and "customer_id" not in b:
        b["branch_id"] = str(MAIN["id"])
    r = api.post("/orders", b, who)
    assert r.status_code == 201, r.text
    return r.json()


def oid(d: dict) -> str:
    return d["order"]["id"]


def pay(api, order_id, amount, method="Cash", who="owner", **extra):
    return api.post(
        f"/orders/{order_id}/payments", {"amount": str(amount), "method": method, **extra}, who
    )


def advance(api, order_id, to, who="owner") -> None:
    chain = ["Scheduled", "Picked Up", "Processing", "Ready", "Out for Delivery", "Delivered"]
    for s in chain[: chain.index(to) + 1]:
        r = api.post(f"/orders/{order_id}/status", {"status": s}, who)
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------- 0. rules
def test_mobile_normalisation_rules() -> None:
    from app.core.exceptions import UnprocessableError
    from app.core.orders import normalize_mobile as n

    for raw in (
        "0501234567",
        "501234567",
        "+971501234567",
        "971501234567",
        "00971 50 123 4567",
        "050-123-4567",
    ):
        assert n(raw) == "+971501234567", raw
    assert n("+44 7911 123456") == "+447911123456"
    for bad in ("12345", "abc", "0401234567", "+97141234567", "+971123456789", "05012345", ""):
        with pytest.raises(UnprocessableError):
            n(bad)


def test_payment_arithmetic_and_flow() -> None:
    from app.core import orders as r

    assert r.final_payable(Decimal("100"), Decimal("10"), Decimal("5")) == Decimal("95.00")
    assert r.outstanding(Decimal("95"), Decimal("30")) == Decimal("65.00")
    assert [r.payment_status(Decimal("95"), Decimal(x)) for x in ("0", "30", "95")] == [
        "Unpaid",
        "Partial",
        "Paid",
    ]
    assert r.next_status("New") == "Scheduled" and r.next_status("Out for Delivery") == "Delivered"
    assert r.next_status("Delivered") is None and r.next_status("Cancelled") is None


# ---------------------------------------------------------------- 1. customers
def test_customer_create_normalise_search_update(api, bid) -> None:
    r = api.post("/customers", new_cust(whatsapp="0559876543"), "branch")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["mobile"] == "+971501234567" and c["whatsapp"] == "+971559876543"
    assert c["branch_name"] == "ALSAFA MAIN" and c["order_count"] == 0
    assert (
        api.post("/customers", new_cust(name="Bilal"), "branch").status_code == 409
    )  # same mobile
    for q in ("aisha", "0501234567", "501 234", "+971501234567"):
        j = api.get("/customers", "branch", q=q).json()
        assert j["total"] == 1 and j["items"][0]["id"] == c["id"], q
    assert api.get("/customers", "branch", q="nobody").json()["total"] == 0
    r = api.put(
        f"/customers/{c['id']}",
        new_cust(name="Aisha K.", area="Jumeirah", mobile="0501234567"),
        "branch",
    )
    assert (
        r.status_code == 200 and r.json()["area"] == "Jumeirah" and r.json()["name"] == "Aisha K."
    )


def test_customer_validation_and_duplicates(api, bid) -> None:
    for bad in (
        new_cust(mobile="123"),
        new_cust(name="A"),
        new_cust(whatsapp="x"),
        new_cust(extra="no"),
    ):
        assert (
            api.post("/customers", {**bad, "branch_id": str(bid["JERNAS"])}).status_code == 422
        ), bad
    assert api.post("/customers", new_cust()).status_code == 422  # owner must pick a branch
    ok = api.post("/customers", {**new_cust(), "branch_id": str(bid["JERNAS"])})
    assert ok.status_code == 201
    dup = api.post(
        "/customers",
        {**new_cust(name="Other", mobile="+971 50 123 4567"), "branch_id": str(bid["JERNAS"])},
    )
    assert dup.status_code == 409 and code(dup) == "duplicate_customer"
    assert dup.json()["error"]["fields"]["customer_id"] == [ok.json()["id"]]
    # the same number is a separate record in another branch (customers are branch-scoped)
    assert api.post("/customers", {**new_cust(), "branch_id": str(bid["SATWA"])}).status_code == 201
    # updating onto another customer's number is refused
    second = api.post(
        "/customers",
        {**new_cust(name="Second", mobile="0502222222"), "branch_id": str(bid["JERNAS"])},
    ).json()
    r = api.put(f"/customers/{second['id']}", new_cust(name="Second", mobile="0501234567"))
    assert r.status_code == 409


def test_customer_branch_isolation(api, bid) -> None:
    mine = api.post("/customers", new_cust(), "branch").json()
    theirs = api.post(
        "/customers", new_cust(name="Other Branch", mobile="0503333333"), "other"
    ).json()
    assert api.get(f"/customers/{theirs['id']}", "branch").status_code == 404
    assert (
        api.put(f"/customers/{theirs['id']}", new_cust(mobile="0503333333"), "branch").status_code
        == 404
    )
    assert api.get(f"/customers/{theirs['id']}/orders", "branch").status_code == 404
    assert [c["id"] for c in api.get("/customers", "branch").json()["items"]] == [mine["id"]]
    assert api.get("/customers", "branch", branch_id=str(bid["JERNAS"])).status_code == 403
    assert (
        api.post(
            "/customers",
            {**new_cust(mobile="0504444444"), "branch_id": str(bid["JERNAS"])},
            "branch",
        ).status_code
        == 403
    )
    assert api.get("/customers", "owner").json()["total"] == 2
    assert api.get("/customers", "owner", branch_id=str(bid["JERNAS"])).json()["total"] == 1


# ---------------------------------------------------------------- 2. orders
def test_order_create_numbers_branch_and_customer_link(api, bid, cat) -> None:
    a = place(api, cat, "branch")
    b = place(api, cat, "branch")
    n1, n2 = a["order"]["order_no"], b["order"]["order_no"]
    assert n1.startswith("ORD-") and n1 != n2 and int(n2[4:]) == int(n1[4:]) + 1
    o = a["order"]
    assert (
        o["branch_name"] == "ALSAFA MAIN"
        and o["status"] == "New"
        and o["payment_status"] == "Unpaid"
    )
    assert (
        o["final_payable"] == "100.00"
        and o["outstanding"] == "100.00"
        and a["next_status"] == "Scheduled"
    )
    assert a["history"][0]["to_status"] == "New" and a["history"][0]["changed_by"] == "branch test"
    assert a["created_by_name"] == "branch test"
    cust = api.get(f"/customers/{o['customer_id']}", "branch").json()
    assert (
        cust["order_count"] == 1
        and cust["total_billed"] == "100.00"
        and cust["outstanding"] == "100.00"
    )
    # owner places one for an existing customer: branch comes from the customer
    c = api.post(
        "/customers", {**new_cust(mobile="0505555555"), "branch_id": str(bid["JERNAS"])}
    ).json()
    d = place(api, cat, customer_id=c["id"])
    assert d["order"]["branch_name"] == "JERNAS"
    hist = api.get(f"/customers/{c['id']}/orders").json()
    assert hist["total"] == 1 and hist["items"][0]["order_no"] == d["order"]["order_no"]


def test_order_amount_and_schedule_validation(api, cat) -> None:
    cust = {"new_customer": new_cust(), "branch_id": None}
    bad = [
        {"delivery_date": iso(TODAY - D(days=1))},                               # delivery before pickup
        {"pickup_time": None},                                                    # pickup date without time
        {"order_total": "-5"}, {"discount": "-1"}, {"service_fee": "-1"},
        {"order_total": "0", "service_fee": "0"},                                  # nothing to pay
        {"order_total": "50", "discount": "60"},                                   # discount more than total
        {"order_total": "10.123"},                                                 # three decimals
        {"service_type": "Overnight"}, {"order_date": iso(TODAY + D(days=1))},
        {"category_id": str(uuid.uuid4())}, {"delivery_time": "25:00"},
        {"customer_id": str(uuid.uuid4())},                                        # both customer forms
    ]  # fmt: skip
    for over in bad:
        b = body(
            cat,
            new_customer=new_cust(mobile=f"05{uuid.uuid4().int % 10**8:08d}"),
            branch_id="ignored",
            **over,
        )
        b.pop("branch_id")
        b["branch_id"] = None
        r = api.post("/orders", {k: v for k, v in b.items() if v is not None or k == "pickup_time"})
        assert r.status_code == 422, (over, r.status_code, r.text[:200])
    # no pickup at all (walk-in) is fine; delivery on the pickup minute is fine
    ok = api.post(
        "/orders",
        body(
            cat,
            pickup_date=None,
            pickup_time=None,
            pickup_address=None,
            new_customer=new_cust(),
            branch_id=None,
        )
        | {"branch_id": None},
    )
    assert ok.status_code == 422  # owner without a branch
    del cust


def test_order_without_pickup_and_discount_fee_maths(api, bid, cat) -> None:
    d = place(api, cat, "branch", pickup_date=None, pickup_time=None, pickup_address=None,
              order_total="200", discount="20", service_fee="15.50", service_type="Express")  # fmt: skip
    assert d["order"]["pickup_at"] is None and d["order"]["final_payable"] == "195.50"
    assert d["order"]["service_type"] == "Express"
    same = place(api, cat, "branch", delivery_date=iso(TODAY), delivery_time="10:00")
    assert same["order"]["delivery_at"] == same["order"]["pickup_at"]


def test_order_branch_rules(api, bid, cat) -> None:
    c_other = api.post("/customers", new_cust(mobile="0506666666"), "other").json()
    # a branch user cannot use another branch's customer or force another branch
    r = api.post("/orders", body(cat, customer_id=c_other["id"]), "branch")
    assert r.status_code == 404
    r = api.post(
        "/orders",
        body(cat, new_customer=new_cust(mobile="0507777777"), branch_id=str(bid["JERNAS"])),
        "branch",
    )
    assert r.status_code == 403
    mine = place(api, cat, "branch")
    # branch can never change after creation (fields are forbidden) and other branches cannot see it
    r = api.put(f"/orders/{oid(mine)}", body(cat, branch_id=str(bid["JERNAS"])), "branch")
    assert r.status_code == 422
    assert api.get(f"/orders/{oid(mine)}", "other").status_code == 404
    assert api.get(f"/orders/{oid(mine)}/payments", "other").status_code == 404
    assert (
        api.post(f"/orders/{oid(mine)}/status", {"status": "Scheduled"}, "other").status_code == 404
    )
    assert pay(api, oid(mine), 10, who="other").status_code == 404
    assert api.get("/orders", "other").json()["total"] == 0
    assert api.get("/orders", "other", branch_id=str(bid["ALSAFA MAIN"])).status_code == 403
    assert api.get("/orders", "owner").json()["total"] == 1
    # customer of another branch cannot be attached even by the owner using a mismatched branch
    r = api.post("/orders", body(cat, customer_id=c_other["id"], branch_id=str(bid["ALSAFA MAIN"])))
    assert r.status_code == 422


def test_order_edit_rules(api, cat) -> None:
    d = place(api, cat, "branch", order_total="100")
    i = oid(d)
    pay(api, i, 60, who="branch")
    r = api.put(
        f"/orders/{i}",
        body(cat, order_total="150", notes="add starch", reason="customer asked"),
        "branch",
    )
    assert r.status_code == 200 and r.json()["order"]["final_payable"] == "150.00"
    assert r.json()["order"]["outstanding"] == "90.00" and r.json()["notes"] == "add starch"
    low = api.put(
        f"/orders/{i}", body(cat, order_total="50"), "branch"
    )  # below what is already collected
    assert low.status_code == 422
    assert (
        api.put(
            f"/orders/{i}", body(cat, delivery_date=iso(TODAY - D(days=3))), "branch"
        ).status_code
        == 422
    )
    advance(api, i, "Delivered")
    assert (
        api.put(f"/orders/{i}", body(cat, order_total="151"), "branch").status_code == 409
    )  # locked when delivered


# ---------------------------------------------------------------- 3. status workflow
def test_status_workflow_history_and_no_skipping(api, cat, admin) -> None:
    d = place(api, cat, "branch")
    i = oid(d)
    r = api.post(f"/orders/{i}/status", {"status": "Processing"}, "branch")  # skipping
    assert (
        r.status_code == 409
        and code(r) == "invalid_transition"
        and "Scheduled" in r.json()["error"]["message"]
    )
    assert api.post(f"/orders/{i}/status", {"status": "New"}, "branch").status_code == 409
    assert (
        api.post(f"/orders/{i}/status", {"status": "Cancelled"}, "branch").status_code == 409
    )  # must use cancel
    advance(api, i, "Out for Delivery", "branch")
    done = api.post(
        f"/orders/{i}/status", {"status": "Delivered", "note": "left with guard"}, "branch"
    ).json()
    assert (
        done["order"]["status"] == "Delivered"
        and done["next_status"] is None
        and done["delivered_at"]
    )
    hist = api.get(f"/orders/{i}/status-history", "branch").json()
    assert [h["to_status"] for h in hist] == [
        "New",
        "Scheduled",
        "Picked Up",
        "Processing",
        "Ready",
        "Out for Delivery",
        "Delivered",
    ]
    assert hist[-1]["from_status"] == "Out for Delivery" and hist[-1]["note"] == "left with guard"
    assert all(h["changed_by"] == "branch test" and h["changed_at"] for h in hist)
    assert api.post(f"/orders/{i}/status", {"status": "Delivered"}, "branch").status_code == 409
    # the database enforces the same chain even for a direct write
    e = place(api, cat, "branch")
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute("update public.orders set status = 'Ready' where id = %s", (oid(e),))
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute(
            "update public.orders set amount_collected = 5, payment_status = 'Partial' where id = %s",
            (oid(e),),
        )


def test_cancellation_rules(api, cat, admin) -> None:
    d = place(api, cat, "branch")
    i = oid(d)
    pay(api, i, 40, "Bank Transfer", who="branch")
    assert (
        api.post(
            f"/orders/{i}/cancel", {"reason": "customer changed mind", "confirm": True}, "branch"
        ).status_code
        == 403
    )
    for bad in (
        {"reason": "x", "confirm": True},
        {"reason": "customer changed mind"},
        {"reason": "customer changed mind", "confirm": False},
    ):
        assert api.post(f"/orders/{i}/cancel", bad).status_code == 422, bad
    r = api.post(f"/orders/{i}/cancel", {"reason": "customer changed mind", "confirm": True})
    assert r.status_code == 200
    j = r.json()
    assert (
        j["order"]["status"] == "Cancelled"
        and j["cancel_reason"] == "customer changed mind"
        and j["cancelled_at"]
    )
    assert (
        j["order"]["amount_collected"] == "40.00" and len(j["payments"]) == 1
    )  # payment history is preserved
    assert (
        j["history"][-1]["to_status"] == "Cancelled"
        and j["history"][-1]["note"] == "customer changed mind"
    )
    assert j["can_edit"] is False and j["can_pay"] is False and j["next_status"] is None
    assert pay(api, i, 10).status_code == 409
    assert api.put(f"/orders/{i}", body(d["category_id"])).status_code == 409
    assert api.post(f"/orders/{i}/status", {"status": "Scheduled"}).status_code == 409
    assert (
        api.post(f"/orders/{i}/cancel", {"reason": "again please", "confirm": True}).status_code
        == 409
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute("update public.orders set notes = 'edit' where id = %s", (i,))
    # delivered and out-for-delivery orders cannot be cancelled
    e = place(api, cat)
    advance(api, oid(e), "Out for Delivery")
    assert (
        api.post(
            f"/orders/{oid(e)}/cancel", {"reason": "too late now", "confirm": True}
        ).status_code
        == 409
    )
    # orders are never deleted, payments never changed
    with pytest.raises(psycopg.errors.Error):
        admin.execute("delete from public.order_payments where order_id = %s", (i,))
    with pytest.raises(psycopg.errors.Error):
        admin.execute("update public.order_payments set amount = 1 where order_id = %s", (i,))


# ---------------------------------------------------------------- 4. payments
def test_partial_and_full_payments_and_status(api, cat) -> None:
    d = place(api, cat, "branch", order_total="200", discount="20", service_fee="10")  # final 190
    i = oid(d)
    b = api.get(f"/orders/{i}/balance", "branch").json()
    assert (b["final_payable"], b["amount_collected"], b["outstanding"], b["payment_status"]) == (
        "190.00",
        "0.00",
        "190.00",
        "Unpaid",
    )
    r = pay(api, i, "50.25", "Cash", who="branch", reference="R1")
    assert (
        r.status_code == 201
        and r.json()["outstanding"] == "139.75"
        and r.json()["payment_status"] == "Partial"
    )
    r = pay(api, i, 40, "POS", who="branch")
    assert r.json()["outstanding"] == "99.75" and r.json()["payment_status"] == "Partial"
    over = pay(api, i, "99.76", who="branch")
    assert over.status_code == 422 and "outstanding" in over.json()["error"]["message"]
    done = pay(api, i, "99.75", "Payment Link", who="branch")
    assert done.json()["outstanding"] == "0.00" and done.json()["payment_status"] == "Paid"
    assert pay(api, i, "0.01").status_code == 422  # nothing left to pay
    ps = api.get(f"/orders/{i}/payments", "branch").json()
    assert [(p["amount"], p["method"]) for p in ps] == [
        ("50.25", "Cash"),
        ("40.00", "POS"),
        ("99.75", "Payment Link"),
    ]
    assert ps[0]["reference"] == "R1" and ps[0]["recorded_by"] == "branch test"
    det = api.get(f"/orders/{i}", "branch").json()
    assert (
        det["can_pay"] is False
        and det["order"]["payment_status"] == "Paid"
        and len(det["payments"]) == 3
    )


def test_payment_validation(api, cat) -> None:
    i = oid(place(api, cat))
    for bad in ({"amount": "0", "method": "Cash"}, {"amount": "-5", "method": "Cash"}, {"amount": "5", "method": "Crypto"},
                {"amount": "5.123", "method": "Cash"}, {"amount": "5", "method": "Cash", "payment_date": iso(TODAY + D(days=1))},
                {"amount": "5", "method": "Cash", "payment_date": iso(TODAY - D(days=30))}, {"amount": "5", "method": "Cash", "x": 1}):  # fmt: skip
        assert api.post(f"/orders/{i}/payments", bad).status_code == 422, bad
    assert (
        api.post(f"/orders/{uuid.uuid4()}/payments", {"amount": "5", "method": "Cash"}).status_code
        == 404
    )


def test_duplicate_payment_submit_posts_once(api, cat, admin) -> None:
    i = oid(place(api, cat))
    key = str(uuid.uuid4())
    a = pay(api, i, 30, client_key=key)
    b = pay(api, i, 30, client_key=key)  # double click / retry
    assert a.status_code == 201 and b.status_code == 201
    assert api.get(f"/orders/{i}/balance").json()["amount_collected"] == "30.00"
    assert (
        admin.execute(
            "select count(*) from public.order_payments where order_id = %s", (i,)
        ).fetchone()[0]
        == 1
    )
    other = oid(place(api, cat))
    assert (
        pay(api, other, 30, client_key=key).status_code == 409
    )  # the key belongs to the first order


def test_repeated_order_submit_creates_one_order(api, cat, admin) -> None:
    """A double click or retry with the same key returns the first order, with its new customer and payment, once."""
    key = str(uuid.uuid4())
    n = uuid.uuid4().int % 10**8
    kw = {
        "client_key": key,
        "new_customer": new_cust(name=f"Retry {n}", mobile=f"05{n:08d}"),
        "initial_payment": {"amount": "25.00", "method": "Cash"},
        "branch_id": str(MAIN["id"]),
    }
    a = api.post("/orders", body(cat, **kw), "owner")
    b = api.post("/orders", body(cat, **kw), "owner")  # the browser retried the identical request
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    assert oid(a.json()) == oid(b.json())
    assert len(b.json()["payments"]) == 1
    row = admin.execute(
        "select (select count(*) from public.orders where client_key = %s),"
        " (select count(*) from public.customers where mobile like %s),"
        " (select count(*) from public.order_payments where order_id = %s)",
        (key, f"%{n:08d}", oid(a.json())),
    ).fetchone()
    assert tuple(row) == (1, 1, 1)


def test_initial_payment_when_placing_the_order(api, cat) -> None:
    d = place(
        api,
        cat,
        "branch",
        order_total="100",
        initial_payment={"amount": "40", "method": "Cash", "reference": "deposit"},
    )
    assert (
        d["order"]["amount_collected"] == "40.00"
        and d["order"]["payment_status"] == "Partial"
        and len(d["payments"]) == 1
    )
    full = place(api, cat, "branch", initial_payment={"amount": "100", "method": "POS"})
    assert full["order"]["payment_status"] == "Paid" and full["order"]["outstanding"] == "0.00"
    r = api.post(
        "/orders",
        body(
            cat,
            new_customer=new_cust(mobile="0508888888"),
            branch_id=None,
            initial_payment={"amount": "101", "method": "Cash"},
        )
        | {"branch_id": None},
        "branch",
    )
    assert r.status_code == 422
    assert (
        api.get("/orders", "branch").json()["total"] == 2
    )  # the failed one left nothing behind (single transaction)
    assert api.get("/customers", "branch", q="0508888888").json()["total"] == 0


def test_refund_is_not_enabled(api, cat) -> None:
    i = oid(place(api, cat))
    pay(api, i, 20)
    r = api.post(f"/orders/{i}/refund", {"amount": "20", "reason": "customer request"})
    assert r.status_code == 409 and code(r) == "refund_not_approved"
    assert (
        api.post(
            f"/orders/{i}/refund", {"amount": "20", "reason": "customer request"}, "branch"
        ).status_code
        == 403
    )
    assert api.get(f"/orders/{i}/balance").json()["amount_collected"] == "20.00"
    assert all(o["payment_status"] != "Refunded" for o in api.get("/orders").json()["items"])


def test_payment_summary(api, cat, bid) -> None:
    a, b = place(api, cat, "branch"), place(api, cat, "other")
    pay(api, oid(a), 30, "Cash", who="branch")
    pay(api, oid(a), 20, "POS", who="branch")
    pay(api, oid(b), 10, "Cash", who="other")
    s = api.get("/orders/payments/summary", "owner").json()
    assert (
        s["total"] == "60.00"
        and s["by_method"]["Cash"] == "40.00"
        and s["by_method"]["POS"] == "20.00"
        and s["payment_count"] == 3
    )
    mine = api.get("/orders/payments/summary", "branch").json()
    assert mine["total"] == "50.00" and mine["by_method"]["Cash"] == "30.00"


# ---------------------------------------------------------------- 5. operations (Dubai dates)
def seed_ops(api, cat):
    y, t, tm = TODAY - D(days=1), TODAY, TODAY + D(days=1)
    o = {}
    o["pick_today"] = place(
        api,
        cat,
        "branch",
        pickup_date=iso(t),
        pickup_time="09:00",
        delivery_date=iso(tm),
        delivery_time="12:00",
    )
    o["pick_overdue"] = place(
        api,
        cat,
        "branch",
        pickup_date=iso(y),
        pickup_time="09:00",
        delivery_date=iso(tm),
        delivery_time="12:00",
    )
    o["pick_tomorrow"] = place(
        api,
        cat,
        "branch",
        pickup_date=iso(tm),
        pickup_time="09:00",
        delivery_date=iso(tm + D(days=1)),
        delivery_time="12:00",
    )
    o["deliver_today"] = place(
        api,
        cat,
        "branch",
        pickup_date=iso(y),
        pickup_time="08:00",
        delivery_date=iso(t),
        delivery_time="17:00",
    )
    advance(api, oid(o["deliver_today"]), "Ready", "branch")
    o["deliver_overdue"] = place(
        api,
        cat,
        "branch",
        pickup_date=iso(y - D(days=2)),
        pickup_time="08:00",
        delivery_date=iso(y),
        delivery_time="17:00",
    )
    advance(api, oid(o["deliver_overdue"]), "Processing", "branch")
    o["out"] = place(
        api,
        cat,
        "branch",
        pickup_date=iso(y),
        pickup_time="08:00",
        delivery_date=iso(t),
        delivery_time="19:00",
    )
    advance(api, oid(o["out"]), "Out for Delivery", "branch")
    o["done_late"] = place(
        api,
        cat,
        "branch",
        pickup_date=iso(y - D(days=3)),
        pickup_time="08:00",
        delivery_date=iso(y - D(days=1)),
        delivery_time="17:00",
    )
    advance(api, oid(o["done_late"]), "Delivered", "branch")
    o["cancelled"] = (
        place(
            api,
            cat,
            pickup_date=iso(t),
            pickup_time="11:00",
            delivery_date=iso(t),
            delivery_time="20:00",
            branch=None,
        )
        if False
        else None
    )
    o["no_address"] = place(
        api,
        cat,
        "branch",
        pickup_date=None,
        pickup_time=None,
        pickup_address=None,
        delivery_address=None,
    )
    return o


def nos(j) -> set[str]:
    return {x["order_no"] for x in j["items"]}


def test_operations_views_use_dates_and_status(api, cat) -> None:
    o = seed_ops(api, cat)
    no = lambda k: o[k]["order"]["order_no"]  # noqa: E731
    get = lambda v, **p: api.get(f"/order-operations/{v}", "branch", **p).json()  # noqa: E731
    assert nos(get("pickups_today")) == {no("pick_today")}
    assert nos(get("deliveries_today")) == {no("deliver_today"), no("out")}
    assert nos(get("pending_pickups")) == {
        no("pick_today"),
        no("pick_overdue"),
        no("pick_tomorrow"),
    }
    assert nos(get("overdue_pickups")) == {no("pick_overdue")}
    assert nos(get("processing")) == {no("deliver_overdue")}
    assert nos(get("ready")) == {no("deliver_today")}
    assert nos(get("out_for_delivery")) == {no("out")}
    assert nos(get("overdue_deliveries")) == {no("deliver_overdue")}
    assert no("done_late") not in nos(
        get("overdue_deliveries")
    )  # delivered orders are never overdue
    assert nos(get("incomplete")) == {no("no_address")}
    assert nos(get("pickups_today", date=iso(TODAY + D(days=1)))) == {no("pick_tomorrow")}
    assert get("pickups_today", q="nothing-like-this")["total"] == 0
    first = get("pending_pickups", sort="pickup")["items"]
    assert [x["order_no"] for x in first] == [
        no("pick_overdue"),
        no("pick_today"),
        no("pick_tomorrow"),
    ]
    assert get("pending_pickups", sort="pickup", desc="true")["items"][0]["order_no"] == no(
        "pick_tomorrow"
    )
    row = next(x for x in get("overdue_pickups")["items"] if x["order_no"] == no("pick_overdue"))
    assert row["overdue"] == "pickup"
    counts = api.get("/order-operations/counts", "branch").json()
    assert (
        counts["pickups_today"] == 1
        and counts["overdue_deliveries"] == 1
        and counts["incomplete"] == 1
    )
    assert api.get("/order-operations/nope", "branch").status_code == 422


def test_operations_search_and_branch_isolation(api, cat, bid) -> None:
    mine = place(api, cat, "branch")
    theirs = place(api, cat, "other")
    c = api.get(f"/customers/{mine['order']['customer_id']}", "branch").json()
    for q in (mine["order"]["order_no"], c["name"], c["mobile"][-6:], c["mobile"]):
        assert nos(api.get("/order-operations/pending_pickups", "branch", q=q).json()) == {
            mine["order"]["order_no"]
        }, q
    assert theirs["order"]["order_no"] not in nos(
        api.get("/order-operations/pending_pickups", "branch").json()
    )
    both = nos(api.get("/order-operations/pending_pickups").json())
    assert both == {mine["order"]["order_no"], theirs["order"]["order_no"]}
    assert (
        api.get(
            "/order-operations/pending_pickups", "branch", branch_id=str(bid["JERNAS"])
        ).status_code
        == 403
    )
    assert api.get("/order-operations/counts", "other").json()["pending_pickups"] == 1


def test_orders_list_filters(api, cat, admin) -> None:
    other_cat = str(
        admin.execute("select id from public.service_categories where name='Shoes'").fetchone()[0]
    )
    a = place(
        api,
        cat,
        "branch",
        service_type="Express",
        new_customer=new_cust(name="Zed", mobile="0509000001", area="Marina"),
    )
    b = place(
        api,
        other_cat,
        "branch",
        new_customer=new_cust(name="Amy", mobile="0509000002", area="Satwa"),
    )
    pay(api, oid(b), 100, who="branch")
    advance(api, oid(a), "Processing", "branch")
    f = lambda **p: nos(api.get("/orders", "branch", **p).json())  # noqa: E731
    A, B = a["order"]["order_no"], b["order"]["order_no"]
    assert f() == {A, B} and f(status="Processing") == {A} and f(payment_status="Paid") == {B}
    assert (
        f(service_type="Express") == {A}
        and f(category_id=other_cat) == {B}
        and f(area="marina") == {A}
    )
    assert f(q="Amy") == {B} and f(q=A) == {A} and f(q="0509000002") == {B}
    assert (
        f(date_from=iso(TODAY), date_to=iso(TODAY)) == {A, B}
        and f(date_from=iso(TODAY + D(days=1))) == set()
    )
    assert f(pickup_date=iso(TODAY)) == {A, B} and f(delivery_date=iso(TODAY + D(days=2))) == {A, B}
    assert f(delivery_date=iso(TODAY)) == set()
    j = api.get("/orders", "branch", sort="customer", desc="false", page_size=1).json()
    assert j["total"] == 2 and j["items"][0]["customer_name"] == "Amy"
    assert api.get("/orders", "branch", sort="bogus").status_code == 422
    assert api.get("/orders", "branch", status="Lost").status_code == 422


# ---------------------------------------------------------------- 6. dashboard
def test_dashboard_numbers(api, cat) -> None:
    o = seed_ops(api, cat)
    pay(api, oid(o["pick_today"]), 30, who="branch")
    c = place(api, cat, "branch", order_total="500")
    api.post(
        f"/orders/{oid(c)}/cancel", {"reason": "duplicate order", "confirm": True}
    )  # owner cancels
    d = api.get("/orders/dashboard", "branch").json()
    k = d["kpis"]
    live = [
        x
        for x in api.get("/orders", "branch", page_size=100).json()["items"]
        if x["status"] != "Cancelled"
    ]
    assert k["total_orders"] == len(live) == 8
    assert k["todays_pickups"] == 1 and k["todays_deliveries"] == 2
    assert (
        k["monthly_revenue"] == f"{sum(dec(x['final_payable']) for x in live):.2f}"
    )  # same month: all placed today
    assert (
        k["outstanding_payments"] == f"{sum(dec(x['outstanding']) for x in live):.2f}" == "770.00"
    )
    sec = {s["key"]: s for s in d["sections"]}
    assert list(sec) == ["pickups_today", "deliveries_today", "pending_pickups", "processing", "ready",
                         "overdue_deliveries", "incomplete", "recent"]  # fmt: skip
    assert (
        sec["processing"]["count"] == 1
        and sec["ready"]["count"] == 1
        and sec["incomplete"]["count"] == 1
    )
    assert sec["recent"]["count"] == 9 and len(sec["recent"]["items"]) == 8
    assert (
        api.get("/orders/dashboard", "branch", status="Cancelled").json()["kpis"]["total_orders"]
        == 1
    )
    assert (
        api.get("/orders/dashboard", "branch", service_type="Express").json()["kpis"][
            "total_orders"
        ]
        == 0
    )
    assert api.get("/orders/dashboard", "other").json()["kpis"]["total_orders"] == 0
    assert api.get("/orders/dashboard", "owner").json()["kpis"]["total_orders"] == 8


# ---------------------------------------------------------------- 7. reports and exports
def rep(api, key, who="owner", **p):
    p.setdefault("date_from", iso(TODAY))
    p.setdefault("date_to", iso(TODAY))
    r = api.get(f"/orders/reports/{key}", who, **p)
    assert r.status_code == 200, r.text
    return r.json()


def summ(j) -> dict:
    return {s["label"]: s["value"] for s in j["summary"]}


@pytest.fixture()
def sample(api, cat, admin):
    shoes = str(
        admin.execute("select id from public.service_categories where name='Shoes'").fetchone()[0]
    )
    a = place(api, cat, "branch", order_total="200", service_type="Express")  # 200, pays 200
    b = place(api, shoes, "branch", order_total="100", discount="10")  # 90, pays 30
    c = place(api, cat, "other", order_total="60", service_fee="5")  # 65, pays 0
    x = place(api, cat, "branch", order_total="999")  # cancelled
    pay(api, oid(a), 200, who="branch")
    pay(api, oid(b), 30, "POS", who="branch")
    pay(api, oid(x), 50, who="branch")
    api.post(f"/orders/{oid(x)}/cancel", {"reason": "duplicate order", "confirm": True})
    advance(api, oid(a), "Delivered", "branch")
    return a, b, c, x


def test_order_report_totals(api, sample) -> None:
    j = rep(api, "order_summary")
    s = summ(j)
    assert (s["Order count"], s["Completed orders"], s["Cancelled orders"]) == (4, 1, 1)
    assert (s["Standard orders"], s["Express orders"]) == (2, 1)
    assert (
        s["Revenue (AED)"] == "355.00"
        and s["Collections (AED)"] == "230.00"
        and s["Outstanding payments (AED)"] == "125.00"
    )
    assert (
        s["Average order value (AED)"] == "118.33"
        and s["Held on cancelled orders (AED)"] == "50.00"
    )
    assert dec(s["Revenue (AED)"]) - dec(s["Collections (AED)"]) == dec(
        s["Outstanding payments (AED)"]
    )
    cats = {r["category"]: r for r in rep(api, "orders_by_category", page_size=200)["rows"]}
    assert (
        cats["Wash & Iron"]["revenue"] == "265.00"
        and cats["Shoes"]["collected"] == "30.00"
        and cats["Shoes"]["outstanding"] == "60.00"
    )
    types = {r["service_type"]: r for r in rep(api, "orders_by_type")["rows"]}
    assert (
        types["Express"]["orders"] == 1
        and types["Standard"]["orders"] == 3
        and types["Express"]["revenue"] == "200.00"
    )
    br = {r["branch"]: r for r in rep(api, "orders_by_branch", page_size=200)["rows"]}
    assert br["ALSAFA MAIN"]["revenue"] == "290.00" and br["JERNAS"]["revenue"] == "65.00"
    day = rep(api, "orders_trend")["rows"]
    assert len(day) == 1 and day[0]["orders"] == 4
    assert rep(api, "orders_trend", period="week")["rows"][0]["period"].startswith("Week of ")
    pm = {r["method"]: r["total"] for r in rep(api, "order_payments_by_method")["rows"]}
    assert pm["Cash"] == "250.00" and pm["POS"] == "30.00" and pm["Bank Transfer"] == "0.00"
    out = rep(api, "outstanding_orders", page_size=200)
    assert summ(out)["Outstanding (AED)"] == "125.00" and len(out["rows"]) == 2
    lst = rep(api, "orders_list", page_size=200)
    assert lst["total"] == 4 and {r["status"] for r in lst["rows"]} >= {"Delivered", "Cancelled"}
    assert rep(api, "order_summary", status="Delivered")["summary"][0]["value"] == 1
    assert summ(rep(api, "order_summary", payment_status="Unpaid"))["Order count"] == 1


def test_order_reports_branch_scope_and_validation(api, sample, bid) -> None:
    mine = summ(rep(api, "order_summary", "branch"))
    assert mine["Order count"] == 3 and mine["Revenue (AED)"] == "290.00"
    assert summ(rep(api, "order_summary", "other"))["Order count"] == 1
    one = summ(rep(api, "order_summary", "owner", branch_id=str(bid["JERNAS"])))
    assert one["Order count"] == 1 and one["Revenue (AED)"] == "65.00"
    assert (
        api.get("/orders/reports/order_summary", "branch", branch_id=str(bid["JERNAS"])).status_code
        == 403
    )
    assert (
        api.get(
            "/orders/reports/order_summary",
            "owner",
            date_from=iso(TODAY),
            date_to=iso(TODAY - D(days=1)),
        ).status_code
        == 422
    )
    assert (
        api.get(
            "/orders/reports/order_summary", "owner", date_from=iso(TODAY - D(days=400))
        ).status_code
        == 422
    )
    assert api.get("/orders/reports/nope").status_code == 404
    assert api.get("/orders/reports/orders_list", sort="bogus").status_code == 422
    cat_ = api.get("/orders/reports/catalog", "branch").json()
    assert {c["key"] for c in cat_} >= {
        "order_summary",
        "orders_by_category",
        "orders_by_type",
        "orders_list",
    }


def test_order_exports_match_screen_and_respect_branch(api, sample, client) -> None:
    for key in ("order_summary", "orders_by_category", "orders_by_type", "orders_trend", "orders_by_branch",
                "order_payments_by_method", "outstanding_orders", "orders_list"):  # fmt: skip
        screen = rep(api, key, page_size=200)
        r = api.get(
            f"/orders/reports/{key}/export",
            "owner",
            date_from=iso(TODAY),
            date_to=iso(TODAY),
            format="csv",
        )
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv"), key
        assert (
            r.headers["cache-control"] == "no-store" and ".csv" in r.headers["content-disposition"]
        )
        lines = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        flat = {x[0]: x[1] for x in lines if len(x) == 2}
        for s in screen["summary"]:
            if s["value"] is not None:
                exp = f"{dec(s['value']):.2f}" if s["kind"] == "money" else str(s["value"])
                assert flat[s["label"]] == exp, (key, s["label"])
    # the Excel file opens and carries the same rows
    from openpyxl import load_workbook  # noqa: PLC0415

    x = api.get(
        "/orders/reports/orders_list/export",
        "owner",
        date_from=iso(TODAY),
        date_to=iso(TODAY),
        format="xlsx",
    )
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    cells = list(load_workbook(io.BytesIO(x.content)).active.iter_rows(values_only=True))
    assert sum(1 for c in cells if c and isinstance(c[0], str) and c[0].startswith("ORD-")) == 4
    # a branch user exports only their own branch; another branch or no login is refused
    mine = api.get(
        "/orders/reports/orders_list/export",
        "branch",
        date_from=iso(TODAY),
        date_to=iso(TODAY),
        format="csv",
    )
    text = mine.content.decode("utf-8-sig")
    assert (
        mine.status_code == 200
        and text.count("ORD-") == 3
        and "JERNAS" not in text.split("Branch,")[1].split("\n")[0] + ""
    )
    assert "JERNAS" not in text
    assert (
        api.get(
            "/orders/reports/orders_list/export",
            "branch",
            branch_id="00000000-0000-0000-0000-000000000000",
        ).status_code
        == 403
    )
    assert client.get(f"{API}/orders/reports/orders_list/export").status_code == 401
    assert api.get("/orders/reports/orders_list/export", "owner", format="pdf").status_code == 422


# ---------------------------------------------------------------- 8. access control
def test_everything_needs_a_login(client, api, cat) -> None:
    i = oid(place(api, cat))
    for path in ("/orders", "/orders/dashboard", f"/orders/{i}", f"/orders/{i}/payments", "/orders/service-categories",
                 "/customers", "/order-operations/pending_pickups", "/order-operations/counts", "/orders/reports/catalog",
                 "/orders/payments/summary"):  # fmt: skip
        assert client.get(f"{API}{path}").status_code == 401, path
    assert client.post(f"{API}/orders", json={}).status_code == 401
    assert client.post(f"{API}/orders/{i}/payments", json={}).status_code == 401


def test_categories_are_configurable_data(api, admin, cat) -> None:
    names = [c["name"] for c in api.get("/orders/service-categories", "branch").json()]
    assert names == [
        "Wash & Fold",
        "Wash & Iron",
        "Ironing",
        "Dry Cleaning",
        "Shoes",
        "Curtains",
        "Carpets",
        "Bulky",
        "Other",
    ]
    admin.execute("update public.service_categories set is_active = false where name = 'Bulky'")
    try:
        bulky = next(
            c["id"] for c in api.get("/orders/service-categories").json() if c["name"] == "Bulky"
        )
        assert (
            api.post(
                "/orders",
                body(bulky, new_customer=new_cust(), branch_id=None) | {"branch_id": None},
                "branch",
            ).status_code
            == 422
        )
    finally:
        admin.execute("update public.service_categories set is_active = true where name = 'Bulky'")


def test_database_row_security_blocks_other_branches(api, cat, app_url, bid, other_user) -> None:
    """Even a direct SQL session as the restricted role cannot see another branch's orders or customers."""
    import json  # noqa: PLC0415

    mine = place(api, cat, "branch")
    claims_json = json.dumps({"sub": str(other_user), "role": "authenticated"})
    with psycopg.connect(app_url, autocommit=False) as c:
        c.execute("select set_config('request.jwt.claims', %s, true)", (claims_json,))
        c.execute("set local role authenticated")
        assert c.execute("select count(*) from public.orders").fetchone()[0] == 0
        assert c.execute("select count(*) from public.customers").fetchone()[0] == 0
        assert c.execute("select count(*) from public.order_payments").fetchone()[0] == 0
        assert c.execute("select count(*) from public.order_status_history").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("delete from public.orders where id = %s", (oid(mine),))
        c.rollback()
    del bid


# ---------------------------------------------------------------- 9. integration with the existing ERP
def test_orders_do_not_touch_finance_or_daily_reports(api, admin, bid, cat) -> None:
    ob = {
        "as_of_date": iso(TODAY - D(days=5)), "receipts_bank": "ENBD", "enbd_balance": "10000.00", "adcb_balance": "5000.00",
        "pos_pending": "0.00", "savings_brought_forward": "0.00", "supplier_dues": [],
        "branch_cash": [{"branch_id": str(i), "amount": "0"} for i in bid.values()],
    }  # fmt: skip
    assert api.put("/opening-balances", ob).status_code == 200
    admin.execute(
        "insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received) values (%s,%s,500,5,500)",
        (TODAY - D(days=1), bid["ALSAFA MAIN"]),
    )
    snap = lambda: (  # noqa: E731
        api.get("/cash-banks/summary").json(),
        api.get("/dashboard/owner", mode="day", date=iso(TODAY - D(days=1))).json()["kpis"],
        api.get("/reports/overview", date_from=iso(TODAY - D(days=5)), date_to=iso(TODAY)).json()["kpis"],
        api.get("/reports/ledger", date_from=iso(TODAY - D(days=5)), date_to=iso(TODAY)).json()["total"],
        admin.execute("select count(*) from public.daily_reports").fetchone()[0],
    )  # fmt: skip
    before = snap()
    d = place(
        api, cat, "branch", order_total="300", initial_payment={"amount": "100", "method": "Cash"}
    )
    pay(api, oid(d), 50, "POS", who="branch")
    pay(api, oid(d), 150, "Bank Transfer")
    assert snap() == before  # no ledger entry, no daily-report sales, no balance movement
    assert api.get(f"/orders/{oid(d)}").json()["order"]["payment_status"] == "Paid"


def test_audit_trail_records_orders_and_payments(api, admin, cat) -> None:
    d = place(api, cat, "branch", initial_payment={"amount": "10", "method": "Cash"})
    i = oid(d)
    advance(api, i, "Scheduled", "branch")
    rows = admin.execute(
        "select table_name, action from public.audit_log where record_id = %s or new_values->>'order_id' = %s",
        (i, i),
    ).fetchall()
    tables = {r[0] for r in rows}
    assert {"orders", "order_payments"} <= tables and ("orders", "UPDATE") in set(rows)
    act = api.get(
        "/reports/activity", date_from=iso(TODAY), date_to=iso(TODAY), page_size=200
    ).json()
    assert {"Orders", "Order Payments"} <= {r["module"] for r in act["rows"]}
    assert any(
        r["record"] == d["order"]["order_no"] for r in act["rows"] if r["module"] == "Orders"
    )
    own = api.get("/reports/activity", "branch", date_from=iso(TODAY), date_to=iso(TODAY))
    assert own.status_code == 403  # the Owner-only activity history stays Owner-only


def test_permission_matrix_for_orders() -> None:
    from app.core.permissions import Action, Module, Role, can  # noqa: PLC0415

    for m in (Module.ORDERS, Module.CUSTOMERS, Module.ORDER_PAYMENTS):
        assert can(Role.OWNER, m, Action.READ) and can(Role.BRANCH_USER, m, Action.READ)
    assert can(Role.OWNER, Module.ORDERS, Action.MANAGE) and not can(
        Role.BRANCH_USER, Module.ORDERS, Action.MANAGE
    )
    assert not can(Role.BRANCH_USER, Module.ORDER_PAYMENTS, Action.MANAGE)
    assert can(Role.BRANCH_USER, Module.ORDERS, Action.EXPORT)
    assert not can(Role.BRANCH_USER, Module.ORDERS, Action.DELETE) and not can(
        Role.OWNER, Module.ORDERS, Action.DELETE
    )
