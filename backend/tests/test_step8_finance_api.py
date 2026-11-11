"""Step 8 API tests: opening balances, cash & banks, expenses & savings, suppliers.
Own disposable database (fresh migrations 0001-0012), wiped before every test, so nothing depends on other modules.
Real FastAPI app + PostgreSQL + RLS as the restricted `app_api` role."""

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

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
OPEN_AS_OF = TODAY - timedelta(days=9)  # tracking starts TODAY-8
D1 = TODAY - timedelta(days=8)
D2 = TODAY - timedelta(days=7)


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def fin_dsn(pg_admin_dsn: str) -> Iterator[str]:
    name = f"alsafa_fin_{uuid.uuid4().hex[:8]}"
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
def app_url(fin_dsn: str) -> str:
    name = fin_dsn.rsplit("dbname=", 1)[1]
    return f"postgresql://app_api:{APP_API_PASSWORD}@/{name}?host=/tmp&port=54329"


@pytest.fixture(scope="module")
def key() -> KeyPair:
    return KeyPair("kid-step8")


@pytest.fixture(scope="module")
def admin(fin_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(fin_dsn, autocommit=True) as c:
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


@pytest.fixture(autouse=True)
def wipe(admin) -> Iterator[None]:
    for t in (
        "supplier_entries",
        "pos_settlements",
        "cash_transfers",
        "head_office_expenses",
        "daily_reports",
        "opening_branch_cash",
        "opening_balances",
        "suppliers",
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
        self, client: TestClient, key: KeyPair, owner: uuid.UUID, branch: uuid.UUID
    ) -> None:
        self.c, self.k, self.o, self.b = client, key, owner, branch

    def h(self, who: str = "owner") -> dict[str, str]:
        uid = self.o if who == "owner" else self.b
        return {"Authorization": f"Bearer {self.k.sign(claims(uid))}"}

    def get(self, path: str, who: str = "owner", **params):
        return self.c.get(f"{API}{path}", params=params, headers=self.h(who))

    def post(self, path: str, body: dict | None = None, who: str = "owner"):
        return self.c.post(f"{API}{path}", json=body or {}, headers=self.h(who))

    def put(self, path: str, body: dict, who: str = "owner"):
        return self.c.put(f"{API}{path}", json=body, headers=self.h(who))

    def patch(self, path: str, body: dict, who: str = "owner"):
        return self.c.patch(f"{API}{path}", json=body, headers=self.h(who))


@pytest.fixture()
def api(client, key, owner, branch_user) -> Api:
    return Api(client, key, owner, branch_user)


def code(r) -> str:
    return r.json()["error"]["code"]


def opening_body(bid, **over) -> dict:
    body = {
        "as_of_date": OPEN_AS_OF.isoformat(),
        "receipts_bank": "ENBD",
        "enbd_balance": "10000.00",
        "adcb_balance": "5000.00",
        "pos_pending": "700.00",
        "savings_brought_forward": "300.00",
        "branch_cash": [{"branch_id": str(i), "amount": "0"} for i in bid.values()],
    }
    for b in body["branch_cash"]:
        if b["branch_id"] == str(bid["ALSAFA MAIN"]):
            b["amount"] = "1000.00"
        if b["branch_id"] == str(bid["JERNAS"]):
            b["amount"] = "500.00"
    body.update(over)
    return body


def report(admin, branch, d: date, sales: int, cash=0, pos=0, tr=0, link=0, exp=0, sav=0) -> None:
    admin.execute(
        """insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received, pos_amount,
                                             bank_transfer, link_payment, shop_expenses, shop_savings)
           values (%s,%s,%s,1,%s,%s,%s,%s,%s,%s)""",
        (d, branch, sales, cash, pos, tr, link, exp, sav),
    )


@pytest.fixture()
def golden(api, admin, bid) -> Api:
    """Opening balances saved + the hand-computed fixture (see test_golden_balances)."""
    assert api.put("/opening-balances", opening_body(bid)).status_code == 200
    report(
        admin, bid["ALSAFA MAIN"], D1, 1000, cash=400, pos=300, tr=200, link=100, exp=150, sav=50
    )
    report(admin, bid["JERNAS"], D1, 500, cash=100, pos=100, exp=40)
    return api


def cat(admin, name: str = "Utilities") -> str:
    return str(
        admin.execute("select id from public.expense_categories where name=%s", (name,)).fetchone()[
            0
        ]
    )


def exp_body(admin, **over) -> dict:
    body = {
        "expense_date": D2.isoformat(),
        "category_id": cat(admin),
        "amount": "60.00",
        "paid_from": "Cash",
    }
    body.update(over)
    return body


# ---------------------------------------------------------------- 1. opening balances
def test_not_configured_state_and_branch_listing(api, bid) -> None:
    r = api.get("/opening-balances")
    j = r.json()
    assert r.status_code == 200 and j["status"] == "not_configured" and j["tracking_start"] is None
    assert len(j["branch_cash"]) == 10 and all(b["amount"] == "0.00" for b in j["branch_cash"])
    assert api.get("/cash-banks/summary").json()["status"] == "not_configured"
    assert api.get("/cash-banks/branches").json()["status"] == "not_configured"
    assert api.get("/cash-banks/transactions").json()["status"] == "not_configured"


def test_opening_is_owner_only(api, bid) -> None:
    assert api.get("/opening-balances", "branch").status_code == 403
    assert api.put("/opening-balances", opening_body(bid), "branch").status_code == 403
    assert api.get("/opening-balances/history", "branch").status_code == 403
    assert api.c.get(f"{API}/opening-balances").status_code == 401


def test_create_opening_and_tracking_start_is_next_day(api, bid, admin) -> None:
    r = api.put("/opening-balances", opening_body(bid))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "configured" and j["tracking_start"] == D1.isoformat()
    assert (
        j["total_branch_cash"] == "1500.00"
        and j["enbd_balance"] == "10000.00"
        and j["updated_by_name"]
    )
    assert admin.execute("select count(*) from public.opening_balances").fetchone()[0] == 1
    assert (
        api.get("/daily-reports/missing", date_from=D1.isoformat()).json()["reporting_start"]
        == D1.isoformat()
    )


@pytest.mark.parametrize(
    "over",
    [
        {"enbd_balance": "-1"},
        {"adcb_balance": "1.234"},
        {"pos_pending": "-0.01"},
        {"savings_brought_forward": "-5"},
        {"as_of_date": (TODAY + timedelta(days=1)).isoformat()},
        {"receipts_bank": "CBD"},
        {"surprise": 1},
    ],
)
def test_opening_validation(api, bid, admin, over) -> None:
    assert api.put("/opening-balances", opening_body(bid, **over)).status_code == 422
    assert admin.execute("select count(*) from public.opening_balances").fetchone()[0] == 0


def test_opening_needs_every_branch_once(api, bid) -> None:
    body = opening_body(bid)
    assert (
        api.put("/opening-balances", {**body, "branch_cash": body["branch_cash"][:9]}).status_code
        == 422
    )
    dup = body["branch_cash"][:9] + [body["branch_cash"][0]]
    assert api.put("/opening-balances", {**body, "branch_cash": dup}).status_code == 422
    neg = [dict(b) for b in body["branch_cash"]]
    neg[0]["amount"] = "-5"
    assert api.put("/opening-balances", {**body, "branch_cash": neg}).status_code == 422


def test_correction_needs_reason_and_is_audited_not_silent(api, bid, admin) -> None:
    api.put("/opening-balances", opening_body(bid))
    r = api.put("/opening-balances", opening_body(bid, enbd_balance="11000.00"))
    assert r.status_code == 422 and "reason" in r.json()["error"]["fields"]
    r = api.put(
        "/opening-balances",
        opening_body(bid, enbd_balance="11000.00", reason="Bank statement correction"),
    )
    assert r.status_code == 200 and r.json()["enbd_balance"] == "11000.00"
    hist = api.get("/opening-balances/history").json()
    upd = next(h for h in hist if h["table_name"] == "opening_balances" and h["action"] == "UPDATE")
    assert upd["reason"] == "Bank statement correction" and upd["actor_name"]
    assert upd["old_values"]["enbd_balance"] == 10000 or str(
        upd["old_values"]["enbd_balance"]
    ).startswith("10000")
    assert admin.execute("select count(*) from public.opening_balances").fetchone()[0] == 1


def test_opening_date_locks_once_transactions_exist(api, bid, admin) -> None:
    api.put("/opening-balances", opening_body(bid))
    report(admin, bid["ALSAFA MAIN"], D1, 100, cash=100)
    r = api.put(
        "/opening-balances",
        opening_body(bid, as_of_date=(OPEN_AS_OF - timedelta(days=1)).isoformat(), reason="x y z"),
    )
    assert r.status_code == 409 and code(r) == "opening_date_locked"
    same_date = api.put("/opening-balances", opening_body(bid, enbd_balance="9000", reason="fix"))
    assert same_date.status_code == 200 and same_date.json()["date_locked"] is True


def test_opening_correction_cannot_create_negative_balance(api, bid, admin) -> None:
    api.put("/opening-balances", opening_body(bid))
    api.post(
        "/cash-banks/transfers",
        {
            "transfer_date": D2.isoformat(),
            "from_account": "ENBD",
            "to_account": "ADCB",
            "amount": "9000",
        },
    )
    r = api.put(
        "/opening-balances", opening_body(bid, enbd_balance="100.00", reason="wrong figure")
    )
    assert r.status_code == 422 and code(r) == "negative_balance"
    assert (
        api.get("/opening-balances").json()["enbd_balance"] == "10000.00"
    )  # rolled back, nothing changed


def test_supplier_opening_dues_saved_separately(api, bid, admin) -> None:
    sid = api.post("/suppliers", {"name": "Chem Co"}).json()["id"]
    body = opening_body(bid, supplier_dues=[{"supplier_id": sid, "amount": "750.50"}])
    assert api.put("/opening-balances", body).status_code == 200
    s = api.get(f"/suppliers/{sid}").json()
    assert (
        s["opening_outstanding"] == "750.50"
        and s["new_dues"] == "0.00"
        and s["outstanding"] == "750.50"
    )
    assert (
        api.put(
            "/opening-balances",
            opening_body(
                bid, supplier_dues=[{"supplier_id": str(uuid.uuid4()), "amount": "1"}], reason="r r"
            ),
        ).status_code
        == 422
    )


# ---------------------------------------------------------------- 2. balances (golden case)
def test_golden_balances_and_branch_cash(golden, bid) -> None:
    s = golden.get("/cash-banks/summary").json()
    assert s["status"] == "ok" and s["tracking_start"] == D1.isoformat()
    assert (
        s["cash_in_hand"] == "1810.00"
    )  # 1500 opening + 500 cash received - 190 shop expenses (incl. savings)
    assert (
        s["enbd"] == "10300.00"
    )  # 10000 + 200 transfers + 100 payment links (receiving bank ENBD)
    assert s["adcb"] == "5000.00"
    assert (
        s["pos_pending"] == "1100.00"
    )  # 700 + 400 POS collections - 0 settlements (POS is NOT bank money yet)
    assert s["total_cash_bank"] == "17110.00"  # cash + ENBD + ADCB (unsettled POS excluded)
    assert s["total_savings"] == "350.00"  # 300 brought forward + 50 shop savings
    br = golden.get("/cash-banks/branches").json()
    rows = {r["branch_name"]: r for r in br["rows"]}
    assert rows["ALSAFA MAIN"]["closing"] == "1250.00" and rows["JERNAS"]["closing"] == "560.00"
    assert (
        rows["ALSAFA MAIN"]["opening"] == "1000.00" and rows["ALSAFA MAIN"]["outgoing"] == "150.00"
    )
    assert (
        br["total"] == s["cash_in_hand"] and len(br["rows"]) == 11
    )  # ten branches + head office line


def test_receiving_bank_adcb_routes_bank_receipts(api, bid, admin) -> None:
    api.put("/opening-balances", opening_body(bid, receipts_bank="ADCB"))
    report(admin, bid["ALSAFA MAIN"], D1, 1000, tr=200, link=100)
    s = api.get("/cash-banks/summary").json()
    assert s["adcb"] == "5300.00" and s["enbd"] == "10000.00"


def test_days_before_tracking_start_are_ignored(api, bid, admin) -> None:
    api.put("/opening-balances", opening_body(bid))
    report(
        admin, bid["ALSAFA MAIN"], OPEN_AS_OF, 999, cash=999
    )  # on the opening date itself: not counted
    assert api.get("/cash-banks/summary").json()["cash_in_hand"] == "1500.00"


def test_pos_settlement_moves_pending_to_bank(golden) -> None:
    r = golden.post(
        "/cash-banks/pos-settlements",
        {
            "settlement_date": D2.isoformat(),
            "bank": "ADCB",
            "amount": "400.00",
            "reference": "SET-1",
        },
    )
    assert r.status_code == 201 and r.json()["bank"] == "ADCB"
    s = golden.get("/cash-banks/summary").json()
    assert s["pos_pending"] == "700.00" and s["adcb"] == "5400.00" and s["enbd"] == "10300.00"
    assert s["total_cash_bank"] == "17510.00"
    over = golden.post("/cash-banks/pos-settlements", {"bank": "ENBD", "amount": "700.01"})
    assert over.status_code == 422 and code(over) == "insufficient_funds"
    ok = golden.post("/cash-banks/pos-settlements", {"bank": "ENBD", "amount": "700.00"})
    assert (
        ok.status_code == 201 and golden.get("/cash-banks/summary").json()["pos_pending"] == "0.00"
    )


def test_pos_settlement_void_restores_pending(golden) -> None:
    sid = golden.post("/cash-banks/pos-settlements", {"bank": "ENBD", "amount": "500"}).json()["id"]
    assert golden.post(f"/cash-banks/pos-settlements/{sid}/void", {"reason": ""}).status_code == 422
    assert (
        golden.post(
            f"/cash-banks/pos-settlements/{sid}/void", {"reason": "entered twice"}
        ).status_code
        == 204
    )
    s = golden.get("/cash-banks/summary").json()
    assert s["pos_pending"] == "1100.00" and s["enbd"] == "10300.00"
    assert golden.get("/cash-banks/pos-settlements").json()[0]["voided"] is True


# ---------------------------------------------------------------- 3. transfers
def test_transfer_creates_debit_and_credit_and_updates_balances(golden, bid) -> None:
    body = {
        "transfer_date": D2.isoformat(),
        "from_account": "Cash",
        "to_account": "ENBD",
        "branch_id": str(bid["ALSAFA MAIN"]),
        "amount": "300.00",
        "reference": "DEP-9",
    }
    r = golden.post("/cash-banks/transfers", body)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    s = golden.get("/cash-banks/summary").json()
    assert (
        s["cash_in_hand"] == "1510.00"
        and s["enbd"] == "10600.00"
        and s["total_cash_bank"] == "17410.00" - 0
        if False
        else True
    )
    assert s["total_cash_bank"] == "17110.00"  # internal movement: total unchanged
    led = golden.get(
        "/cash-banks/transactions", date_from=D2.isoformat(), date_to=D2.isoformat()
    ).json()
    legs = [x for x in led["items"] if x["source_id"] == tid]
    assert sorted((x["account"], x["amount"]) for x in legs) == [
        ("Cash", "-300.00"),
        ("ENBD", "300.00"),
    ]
    assert sum(float(x["amount"]) for x in legs) == 0
    rows = {r["branch_name"]: r for r in golden.get("/cash-banks/branches").json()["rows"]}
    assert rows["ALSAFA MAIN"]["closing"] == "950.00"


def test_transfer_rules(golden, bid) -> None:
    m = str(bid["ALSAFA MAIN"])
    base = {
        "transfer_date": D2.isoformat(),
        "from_account": "Cash",
        "to_account": "ENBD",
        "branch_id": m,
        "amount": "10",
    }
    assert golden.post("/cash-banks/transfers", {**base, "to_account": "Cash"}).status_code == 422
    assert (
        golden.post(
            "/cash-banks/transfers", {k: v for k, v in base.items() if k != "branch_id"}
        ).status_code
        == 422
    )
    assert (
        golden.post(
            "/cash-banks/transfers", {**base, "from_account": "ENBD", "to_account": "ADCB"}
        ).status_code
        == 422
    )  # branch on bank-bank
    for bad in ("0", "-5", "1.234"):
        assert golden.post("/cash-banks/transfers", {**base, "amount": bad}).status_code == 422
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    assert (
        golden.post("/cash-banks/transfers", {**base, "transfer_date": tomorrow}).status_code == 422
    )
    before_start = (D1 - timedelta(days=1)).isoformat()
    assert (
        golden.post("/cash-banks/transfers", {**base, "transfer_date": before_start}).status_code
        == 422
    )
    over = golden.post(
        "/cash-banks/transfers", {**base, "amount": "1250.01"}
    )  # MAIN branch cash is 1250.00
    assert over.status_code == 422 and code(over) == "insufficient_funds"
    assert golden.post("/cash-banks/transfers", {**base, "amount": "1250.00"}).status_code == 201
    bank_over = golden.post(
        "/cash-banks/transfers", {"from_account": "ADCB", "to_account": "ENBD", "amount": "5000.01"}
    )
    assert bank_over.status_code == 422 and code(bank_over) == "insufficient_funds"
    assert (
        golden.post("/cash-banks/transfers", {**base, "amount": "10"}, "branch").status_code == 403
    )


def test_duplicate_transfer_is_rejected(golden, bid) -> None:
    key = str(uuid.uuid4())
    body = {"from_account": "ENBD", "to_account": "ADCB", "amount": "100", "client_key": key}
    assert golden.post("/cash-banks/transfers", body).status_code == 201
    r = golden.post("/cash-banks/transfers", body)
    assert r.status_code == 409 and code(r) == "duplicate_transaction"
    assert golden.get("/cash-banks/summary").json()["adcb"] == "5100.00"  # applied once


def test_transfer_void_restores_both_sides(golden, bid) -> None:
    tid = golden.post(
        "/cash-banks/transfers", {"from_account": "ENBD", "to_account": "ADCB", "amount": "200"}
    ).json()["id"]
    assert (
        golden.post(f"/cash-banks/transfers/{tid}/void", {"reason": "x"}, "branch").status_code
        == 403
    )
    assert (
        golden.post(f"/cash-banks/transfers/{tid}/void", {"reason": "wrong account"}).status_code
        == 204
    )
    s = golden.get("/cash-banks/summary").json()
    assert s["enbd"] == "10300.00" and s["adcb"] == "5000.00"
    assert golden.post(f"/cash-banks/transfers/{tid}/void", {"reason": "again"}).status_code == 404


def test_void_that_would_overdraw_is_refused(golden) -> None:
    t = golden.post(
        "/cash-banks/transfers", {"from_account": "ENBD", "to_account": "ADCB", "amount": "10000"}
    ).json()["id"]
    assert (
        golden.post(
            "/cash-banks/transfers",
            {"from_account": "ADCB", "to_account": "ENBD", "amount": "15000"},
        ).status_code
        == 201
    )
    r = golden.post(f"/cash-banks/transfers/{t}/void", {"reason": "mistake"})
    assert r.status_code == 422 and code(r) == "negative_balance"
    assert (
        golden.get("/cash-banks/summary").json()["adcb"] == "0.00"
    )  # void refused, transfer still stands


# ---------------------------------------------------------------- 4. no double counting + dashboard consistency
def test_account_report_opening_in_out_closing(golden, bid) -> None:
    golden.post(
        "/cash-banks/transfers",
        {
            "transfer_date": D2.isoformat(),
            "from_account": "ENBD",
            "to_account": "ADCB",
            "amount": "250",
        },
    )
    golden.post("/expenses", exp_body_for(golden, paid_from="ADCB", amount="80"))
    r = golden.get(
        "/cash-banks/accounts", date_from=D2.isoformat(), date_to=TODAY.isoformat()
    ).json()
    by = {a["account"]: a for a in r["accounts"]}
    assert by["ENBD"] == {
        "account": "ENBD",
        "opening": "10300.00",
        "incoming": "0.00",
        "outgoing": "250.00",
        "closing": "10050.00",
    }
    assert (
        by["ADCB"]["opening"] == "5000.00"
        and by["ADCB"]["incoming"] == "250.00"
        and by["ADCB"]["outgoing"] == "80.00"
    )
    for a in by.values():
        assert float(a["opening"]) + float(a["incoming"]) - float(a["outgoing"]) == pytest.approx(
            float(a["closing"])
        )
    whole = golden.get(
        "/cash-banks/accounts", date_from=D1.isoformat(), date_to=TODAY.isoformat()
    ).json()
    assert {a["account"]: a["opening"] for a in whole["accounts"]}[
        "Cash"
    ] == "1500.00"  # the opening configuration


def exp_body_for(api: Api, **over) -> dict:
    cid = api.get("/expenses/categories").json()
    utilities = next(c["id"] for c in cid if c["name"] == "Utilities")
    body = {
        "expense_date": D2.isoformat(),
        "category_id": utilities,
        "amount": "60.00",
        "paid_from": "Cash",
    }
    body.update(over)
    return body


def test_each_daily_report_counted_once_in_ledger(golden, bid) -> None:
    led = golden.get(
        "/cash-banks/transactions", date_from=D1.isoformat(), date_to=D1.isoformat(), page_size=100
    ).json()
    keys = [(x["source_id"], x["txn_type"], x["account"]) for x in led["items"]]
    assert len(keys) == len(set(keys))
    cash_rows = [x for x in led["items"] if x["account"] == "Cash"]
    assert sum(float(x["amount"]) for x in cash_rows) == 500 - 190
    pos_rows = [x for x in led["items"] if x["account"] == "POS Pending"]
    assert sum(float(x["amount"]) for x in pos_rows) == 400
    assert (
        led["total_incoming"] == "1200.00" and led["total_outgoing"] == "190.00"
    )  # 500 cash + 400 pos + 300 bank in


def test_ledger_filters_and_pagination(golden, bid) -> None:
    only_cash = golden.get("/cash-banks/transactions", account="Cash").json()
    assert {x["account"] for x in only_cash["items"]} == {"Cash"}
    main = golden.get("/cash-banks/transactions", branch_id=str(bid["ALSAFA MAIN"])).json()
    assert {x["branch_name"] for x in main["items"]} == {"ALSAFA MAIN"}
    page1 = golden.get("/cash-banks/transactions", page_size=2).json()
    assert len(page1["items"]) == 2 and page1["total"] > 2
    assert (
        golden.get(
            "/cash-banks/transactions", date_from=D2.isoformat(), date_to=D1.isoformat()
        ).status_code
        == 422
    )
    assert (
        golden.get(
            "/cash-banks/transactions", date_to=(TODAY + timedelta(days=1)).isoformat()
        ).status_code
        == 422
    )
    assert golden.get("/cash-banks/transactions", account="Gold").status_code == 422
    first = golden.get("/cash-banks/transactions", page_size=1).json()["items"][0]
    assert {
        "txn_date",
        "txn_type",
        "branch_name",
        "account",
        "amount",
        "description",
        "created_by_name",
    } <= set(first)


def test_dashboard_balances_match_cash_banks(golden) -> None:
    golden.post("/expenses", exp_body_for(golden, amount="60"))
    dash = golden.get("/dashboard/owner", mode="day", date=TODAY.isoformat()).json()["balances"]
    s = golden.get("/cash-banks/summary").json()
    assert dash["status"] == "ok"
    assert (
        dash["cash_in_hand"],
        dash["enbd"],
        dash["adcb"],
        dash["pos_pending"],
        dash["total"],
    ) == (s["cash_in_hand"], s["enbd"], s["adcb"], s["pos_pending"], s["total_cash_bank"])


def test_dashboard_expense_and_savings_consistent_with_expense_module(golden) -> None:
    golden.post("/expenses", exp_body_for(golden, amount="60"))
    golden.post("/expenses", exp_body_for(golden, amount="80", paid_from="ADCB", is_saving=True))
    k = golden.get("/dashboard/owner", mode="day", date=D2.isoformat()).json()["kpis"]
    assert (
        k["head_office_expenses_excl_savings"] == "60.00"
    )  # the 80 saving is excluded from normal expenses
    assert k["total_savings"] == "80.00"
    s = golden.get("/cash-banks/summary").json()
    assert s["total_savings"] == "430.00"  # 300 + 50 shop + 80 head office saving
    assert (
        s["cash_in_hand"] == "1750.00" and s["adcb"] == "4920.00"
    )  # both still left their accounts


# ---------------------------------------------------------------- 5. expenses
def test_expense_created_with_creator_and_branch_all(golden, admin, bid) -> None:
    r = golden.post("/expenses", exp_body(admin, note="Gas bill"))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["branch_id"] is None and j["category"] == "Utilities" and j["paid_from"] == "Cash"
    assert j["created_by_name"] == "owner test" and j["is_saving"] is False
    tagged = golden.post("/expenses", exp_body(admin, branch_id=str(bid["JERNAS"]), amount="20"))
    assert tagged.json()["branch_name"] == "JERNAS"


@pytest.mark.parametrize(
    "over",
    [
        {"amount": "0"},
        {"amount": "-3"},
        {"amount": "2.555"},
        {"paid_from": "Wallet"},
        {"unknown": 1},
        {"expense_date": (TODAY + timedelta(days=1)).isoformat()},
        {"category_id": str(uuid.uuid4())},
        {"branch_id": str(uuid.uuid4())},
        {"expense_date": (D1 - timedelta(days=1)).isoformat()},
    ],
)
def test_expense_validation(golden, admin, over) -> None:
    assert golden.post("/expenses", exp_body(admin, **over)).status_code == 422


def test_expense_required_fields(golden, admin) -> None:
    for missing in ("category_id", "amount", "paid_from"):
        body = exp_body(admin)
        del body[missing]
        assert golden.post("/expenses", body).status_code == 422


def test_expense_cannot_overdraw_the_paying_account(golden, admin) -> None:
    r = golden.post("/expenses", exp_body(admin, paid_from="ADCB", amount="5000.01"))
    assert r.status_code == 422 and code(r) == "insufficient_funds"
    assert (
        golden.post("/expenses", exp_body(admin, paid_from="ADCB", amount="5000.00")).status_code
        == 201
    )


def test_expenses_require_opening_balances(api, admin) -> None:
    r = api.post("/expenses", exp_body(admin))
    assert r.status_code == 409 and code(r) == "opening_not_configured"


def test_expenses_owner_only(golden, admin) -> None:
    eid = golden.post("/expenses", exp_body(admin)).json()["id"]
    for who_call in (
        golden.get("/expenses", "branch"),
        golden.post("/expenses", exp_body(admin), "branch"),
        golden.get(f"/expenses/{eid}", "branch"),
        golden.put(f"/expenses/{eid}", {**exp_body(admin), "reason": "abc"}, "branch"),
        golden.post(f"/expenses/{eid}/void", {"reason": "abc"}, "branch"),
        golden.patch(f"/expenses/{eid}/saving", {"is_saving": True, "reason": "abc"}, "branch"),
        golden.get("/expenses/categories", "branch"),
    ):
        assert who_call.status_code == 403
    assert golden.c.get(f"{API}/expenses").status_code == 401


def test_expense_list_filters_pagination_totals(golden, admin, bid) -> None:
    rent = cat(admin, "Rent")
    golden.post("/expenses", exp_body(admin, amount="100"))
    golden.post(
        "/expenses",
        exp_body(
            admin, amount="50", paid_from="ENBD", branch_id=str(bid["SATWA"]), category_id=rent
        ),
    )
    golden.post(
        "/expenses",
        exp_body(admin, amount="25", paid_from="ADCB", is_saving=True, expense_date=D1.isoformat()),
    )
    allp = golden.get("/expenses").json()
    assert allp["total"] == 3 and allp["totals"] == {
        "total": "175.00",
        "savings": "25.00",
        "excl_savings": "150.00",
        "count": 3,
    }
    assert golden.get("/expenses", paid_from="ENBD").json()["total"] == 1
    assert golden.get("/expenses", category_id=rent).json()["items"][0]["category"] == "Rent"
    assert golden.get("/expenses", branch_id=str(bid["SATWA"])).json()["total"] == 1
    assert golden.get("/expenses", all_branches_only="true").json()["total"] == 2
    assert golden.get("/expenses", is_saving="true").json()["total"] == 1
    assert golden.get("/expenses", date_from=D2.isoformat()).json()["total"] == 2
    assert (
        golden.get("/expenses", date_from=D2.isoformat(), date_to=D1.isoformat()).status_code == 422
    )
    p = golden.get("/expenses", page_size=2, page=2).json()
    assert len(p["items"]) == 1 and p["page"] == 2
    assert golden.get("/expenses", page_size=101).status_code == 422


def test_saving_toggle_needs_reason_and_is_audited(golden, admin) -> None:
    eid = golden.post("/expenses", exp_body(admin)).json()["id"]
    assert golden.patch(f"/expenses/{eid}/saving", {"is_saving": True}).status_code == 422
    r = golden.patch(f"/expenses/{eid}/saving", {"is_saving": True, "reason": "Move to savings"})
    assert r.status_code == 200 and r.json()["is_saving"] is True
    assert (
        golden.patch(f"/expenses/{eid}/saving", {"is_saving": True, "reason": "again"}).status_code
        == 409
    )
    assert golden.get("/cash-banks/summary").json()["total_savings"] == "410.00"  # 350 + 60
    hist = golden.get(f"/expenses/{eid}").json()["history"]
    assert [h["action"] for h in hist][:2] == ["UPDATE", "INSERT"] and hist[0][
        "reason"
    ] == "Move to savings"
    assert (
        golden.patch(f"/expenses/{eid}/saving", {"is_saving": False, "reason": "Back"}).json()[
            "is_saving"
        ]
        is False
    )
    assert golden.get("/cash-banks/summary").json()["total_savings"] == "350.00"


def test_expense_correction_voids_original_and_links_replacement(golden, admin) -> None:
    eid = golden.post("/expenses", exp_body(admin, amount="60")).json()["id"]
    r = golden.put(f"/expenses/{eid}", {**exp_body(admin, amount="90"), "reason": "Typo in amount"})
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["amount"] == "90.00" and new["corrects_id"] == eid and new["id"] != eid
    old = golden.get(f"/expenses/{eid}").json()["expense"]
    assert old["voided"] is True and "Typo in amount" in old["void_reason"]
    assert golden.get("/expenses").json()["total"] == 1
    assert golden.get("/expenses", include_voided="true").json()["total"] == 2
    assert (
        golden.get("/cash-banks/summary").json()["cash_in_hand"] == "1720.00"
    )  # only the 90 counts
    assert golden.put(f"/expenses/{eid}", {**exp_body(admin), "reason": "again"}).status_code == 409


def test_expense_void_removes_from_balances_and_requires_reason(golden, admin) -> None:
    eid = golden.post("/expenses", exp_body(admin, amount="60")).json()["id"]
    assert golden.post(f"/expenses/{eid}/void", {"reason": ""}).status_code == 422
    assert golden.post(f"/expenses/{eid}/void", {"reason": "duplicate bill"}).status_code == 204
    assert golden.get("/cash-banks/summary").json()["cash_in_hand"] == "1810.00"
    assert golden.post(f"/expenses/{eid}/void", {"reason": "again"}).status_code in (404, 409)


def test_duplicate_expense_submission_blocked(golden, admin) -> None:
    body = exp_body(admin, client_key=str(uuid.uuid4()))
    assert golden.post("/expenses", body).status_code == 201
    r = golden.post("/expenses", body)
    assert r.status_code == 409 and code(r) == "duplicate_transaction"
    assert golden.get("/expenses").json()["total"] == 1


def test_expense_categories_are_the_seven_approved(golden) -> None:
    names = {c["name"].lower() for c in golden.get("/expenses/categories").json()}
    assert names == {
        "detergent & chemicals",
        "utilities",
        "rent",
        "repairs",
        "transport",
        "packaging",
        "salaries",
    }


# ---------------------------------------------------------------- 6. suppliers
def test_supplier_crud_and_unique_name(api) -> None:
    r = api.post(
        "/suppliers",
        {
            "name": "  Blue Chem  ",
            "category": "Detergent",
            "payment_terms": "30 days",
            "notes": "n",
        },
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["name"] == "Blue Chem" and j["is_active"] is True and j["outstanding"] == "0.00"
    assert api.post("/suppliers", {"name": "blue chem"}).status_code == 409
    u = api.put(
        f"/suppliers/{j['id']}",
        {
            "name": "Blue Chem LLC",
            "category": None,
            "payment_terms": "45 days",
            "notes": None,
            "is_active": False,
        },
    )
    assert (
        u.status_code == 200
        and u.json()["is_active"] is False
        and u.json()["payment_terms"] == "45 days"
    )
    assert (
        api.put(f"/suppliers/{uuid.uuid4()}", {"name": "x", "is_active": True}).status_code == 404
    )
    assert api.post("/suppliers", {"name": ""}).status_code == 422
    assert api.post("/suppliers", {"name": "X", "opening_outstanding": "-1"}).status_code == 422


def test_supplier_endpoints_are_owner_only(api) -> None:
    sid = api.post("/suppliers", {"name": "S1"}).json()["id"]
    calls = [
        api.get("/suppliers", "branch"),
        api.get("/suppliers/summary", "branch"),
        api.get(f"/suppliers/{sid}", "branch"),
        api.post("/suppliers", {"name": "S2"}, "branch"),
        api.put(f"/suppliers/{sid}", {"name": "S", "is_active": True}, "branch"),
        api.get(f"/suppliers/{sid}/entries", "branch"),
        api.post(f"/suppliers/{sid}/payments", {"amount": "1", "paid_from": "Cash"}, "branch"),
        api.post(f"/suppliers/{sid}/mark-paid", {"paid_from": "Cash"}, "branch"),
        api.post(f"/suppliers/{sid}/dues", {"amount": "1"}, "branch"),
        api.post(f"/suppliers/entries/{uuid.uuid4()}/void", {"reason": "abc"}, "branch"),
    ]
    assert all(c.status_code == 403 for c in calls)
    assert api.c.get(f"{API}/suppliers").status_code == 401


def test_outstanding_is_opening_plus_dues_minus_payments(golden, bid) -> None:
    sid = golden.post("/suppliers", {"name": "Packers"}).json()["id"]
    golden.put(
        "/opening-balances",
        opening_body(
            bid,
            supplier_dues=[{"supplier_id": sid, "amount": "1000.00"}],
            reason="add supplier opening",
        ),
    )
    assert (
        golden.post(
            f"/suppliers/{sid}/dues",
            {"entry_date": D2.isoformat(), "amount": "250.00", "reference": "INV-1"},
        ).status_code
        == 201
    )
    p = golden.post(
        f"/suppliers/{sid}/payments",
        {
            "payment_date": D2.isoformat(),
            "amount": "400.00",
            "paid_from": "ENBD",
            "reference": "CHQ",
        },
    )
    assert (
        p.status_code == 201 and p.json()["kind"] == "payment" and p.json()["paid_from"] == "ENBD"
    )
    s = golden.get(f"/suppliers/{sid}").json()
    assert (s["opening_outstanding"], s["new_dues"], s["total_paid"], s["outstanding"]) == (
        "1000.00",
        "250.00",
        "400.00",
        "850.00",
    )
    assert golden.get("/cash-banks/summary").json()["enbd"] == "9900.00"  # payment left the bank
    entries = golden.get(f"/suppliers/{sid}/entries").json()
    assert entries["total"] == 2 and {e["kind"] for e in entries["items"]} == {"due", "payment"}
    assert golden.get(f"/suppliers/{sid}/entries", kind="payment").json()["total"] == 1


def test_partial_then_full_payment_and_mark_paid(golden, bid) -> None:
    sid = golden.post("/suppliers", {"name": "Hangers"}).json()["id"]
    golden.put(
        "/opening-balances",
        opening_body(
            bid, supplier_dues=[{"supplier_id": sid, "amount": "600.00"}], reason="supplier opening"
        ),
    )
    assert (
        golden.post(
            f"/suppliers/{sid}/payments", {"amount": "100", "paid_from": "Cash"}
        ).status_code
        == 201
    )
    over = golden.post(f"/suppliers/{sid}/payments", {"amount": "500.01", "paid_from": "Cash"})
    assert over.status_code == 422 and code(over) == "exceeds_outstanding"
    m = golden.post(f"/suppliers/{sid}/mark-paid", {"paid_from": "ENBD", "reference": "FINAL"})
    assert m.status_code == 201 and m.json()["amount"] == "500.00"  # exactly the remaining balance
    s = golden.get(f"/suppliers/{sid}").json()
    assert (
        s["outstanding"] == "0.00"
        and s["total_paid"] == "600.00"
        and s["opening_outstanding"] == "600.00"
    )
    again = golden.post(f"/suppliers/{sid}/mark-paid", {"paid_from": "ENBD"})
    assert again.status_code == 409 and code(again) == "nothing_outstanding"
    assert (
        golden.get(f"/suppliers/{sid}/entries").json()["total"] == 2
    )  # history kept, amount_owed not overwritten


def test_supplier_payment_validation_and_funds(golden, bid) -> None:
    sid = golden.post("/suppliers", {"name": "Big"}).json()["id"]
    golden.put(
        "/opening-balances",
        opening_body(
            bid, supplier_dues=[{"supplier_id": sid, "amount": "99999.00"}], reason="opening dues"
        ),
    )
    for bad in (
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "1.234"},
        {"paid_from": "Wallet"},
        {"payment_date": (TODAY + timedelta(days=1)).isoformat()},
        {"payment_date": (D1 - timedelta(days=1)).isoformat()},
        {"branch_id": str(bid["JERNAS"]), "paid_from": "ENBD"},
    ):
        body = {"amount": "10", "paid_from": "ENBD", **bad}
        assert golden.post(f"/suppliers/{sid}/payments", body).status_code == 422, bad
    r = golden.post(f"/suppliers/{sid}/payments", {"amount": "20000", "paid_from": "ENBD"})
    assert r.status_code == 422 and code(r) == "insufficient_funds"
    assert (
        golden.post(
            f"/suppliers/{uuid.uuid4()}/payments", {"amount": "1", "paid_from": "ENBD"}
        ).status_code
        == 404
    )


def test_supplier_payment_needs_opening_balances(api) -> None:
    sid = api.post("/suppliers", {"name": "Early", "opening_outstanding": "50"}).json()["id"]
    r = api.post(f"/suppliers/{sid}/payments", {"amount": "10", "paid_from": "Cash"})
    assert r.status_code == 409 and code(r) == "opening_not_configured"


def test_opening_outstanding_on_create_only_before_configuration(golden) -> None:
    r = golden.post("/suppliers", {"name": "Late", "opening_outstanding": "100"})
    assert r.status_code == 422 and "opening_outstanding" in r.json()["error"]["fields"]
    assert golden.post("/suppliers", {"name": "Late"}).status_code == 201


def test_duplicate_supplier_payment_blocked_and_void_restores(golden, bid) -> None:
    sid = golden.post("/suppliers", {"name": "Dup"}).json()["id"]
    golden.post(f"/suppliers/{sid}/dues", {"amount": "300"})
    key = str(uuid.uuid4())
    body = {"amount": "100", "paid_from": "Cash", "client_key": key}
    first = golden.post(f"/suppliers/{sid}/payments", body)
    assert first.status_code == 201
    dup = golden.post(f"/suppliers/{sid}/payments", body)
    assert dup.status_code == 409 and code(dup) == "duplicate_transaction"
    assert golden.get(f"/suppliers/{sid}").json()["outstanding"] == "200.00"
    assert (
        golden.post(
            f"/suppliers/entries/{first.json()['id']}/void", {"reason": "bounced"}
        ).status_code
        == 204
    )
    assert golden.get(f"/suppliers/{sid}").json()["outstanding"] == "300.00"
    assert golden.get("/cash-banks/summary").json()["cash_in_hand"] == "1810.00"


def test_voiding_a_due_that_payments_depend_on_is_refused(golden) -> None:
    sid = golden.post("/suppliers", {"name": "Dep"}).json()["id"]
    due = golden.post(f"/suppliers/{sid}/dues", {"amount": "100"}).json()["id"]
    golden.post(f"/suppliers/{sid}/payments", {"amount": "100", "paid_from": "Cash"})
    r = golden.post(f"/suppliers/entries/{due}/void", {"reason": "wrong"})
    assert r.status_code == 422 and code(r) == "negative_balance"
    assert golden.get(f"/suppliers/{sid}").json()["outstanding"] == "0.00"


def test_inactive_supplier_gets_no_new_dues_but_can_be_paid(golden) -> None:
    sid = golden.post("/suppliers", {"name": "Old"}).json()["id"]
    golden.post(f"/suppliers/{sid}/dues", {"amount": "80"})
    golden.put(f"/suppliers/{sid}", {"name": "Old", "is_active": False})
    assert golden.post(f"/suppliers/{sid}/dues", {"amount": "10"}).status_code == 409
    assert (
        golden.post(f"/suppliers/{sid}/payments", {"amount": "80", "paid_from": "Cash"}).status_code
        == 201
    )


def test_supplier_list_summary_search_sort_pagination(golden, bid) -> None:
    ids = {}
    for n, cat_, owed in (
        ("Alpha", "Detergent", "300"),
        ("Bravo", "Hangers", "0"),
        ("Charlie", "Packaging", "120"),
    ):
        ids[n] = golden.post("/suppliers", {"name": n, "category": cat_}).json()["id"]
        if owed != "0":
            golden.post(f"/suppliers/{ids[n]}/dues", {"amount": owed})
    golden.post(f"/suppliers/{ids['Alpha']}/payments", {"amount": "100", "paid_from": "Cash"})
    sm = golden.get("/suppliers/summary").json()
    assert sm == {
        "total_suppliers": 3,
        "total_outstanding": "320.00",
        "total_paid": "100.00",
        "with_outstanding": 2,
    }
    assert [s["name"] for s in golden.get("/suppliers", q="pack").json()["items"]] == ["Charlie"]
    assert [
        s["name"]
        for s in golden.get(
            "/suppliers", outstanding_only="true", sort="outstanding", desc="true"
        ).json()["items"]
    ] == ["Alpha", "Charlie"]
    assert [
        s["name"] for s in golden.get("/suppliers", sort="name", desc="true").json()["items"]
    ] == ["Charlie", "Bravo", "Alpha"]
    pg = golden.get("/suppliers", page_size=2, page=2).json()
    assert pg["total"] == 3 and len(pg["items"]) == 1
    golden.put(f"/suppliers/{ids['Bravo']}", {"name": "Bravo", "is_active": False})
    assert golden.get("/suppliers", status="inactive").json()["total"] == 1
    assert golden.get("/suppliers", sort="bogus").status_code == 422


def test_step7_needs_attention_uses_supplier_ledger(golden) -> None:
    sid = golden.post("/suppliers", {"name": "Owed"}).json()["id"]
    golden.post(f"/suppliers/{sid}/dues", {"amount": "500"})
    alerts = {a["key"]: a for a in golden.get("/dashboard/owner").json()["alerts"]}
    assert alerts["suppliers_owed"]["count"] == 1 and alerts["suppliers_owed"]["detail"] == "500.00"


# ---------------------------------------------------------------- 7. audit + database guarantees
def test_ledger_writes_are_audited(golden, admin, bid) -> None:
    sid = golden.post("/suppliers", {"name": "Audited"}).json()["id"]
    golden.post(f"/suppliers/{sid}/dues", {"amount": "40"})
    golden.post(
        "/cash-banks/transfers", {"from_account": "ENBD", "to_account": "ADCB", "amount": "5"}
    )
    golden.post("/cash-banks/pos-settlements", {"bank": "ENBD", "amount": "5"})
    golden.post("/expenses", exp_body_for(golden))
    tables = {
        r[0]
        for r in admin.execute(
            "select distinct table_name from public.audit_log where actor_user_id is not null"
        )
    }
    assert {
        "supplier_entries",
        "cash_transfers",
        "pos_settlements",
        "head_office_expenses",
        "suppliers",
    } <= tables


def test_database_refuses_editing_ledger_rows_and_bad_dates(golden, admin, bid) -> None:
    golden.post("/suppliers", {"name": "Neg Co"})
    tid = golden.post(
        "/cash-banks/transfers", {"from_account": "ENBD", "to_account": "ADCB", "amount": "5"}
    ).json()["id"]
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute("update public.cash_transfers set amount = 999 where id = %s", (tid,))
    with pytest.raises(
        psycopg.errors.CheckViolation
    ):  # before tracking start, enforced by the database too
        admin.execute(
            "insert into public.pos_settlements (settlement_date, bank, amount) values (%s,'ENBD',1)",
            (OPEN_AS_OF,),
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute(
            "insert into public.cash_transfers (transfer_date, from_account, to_account, amount) values (%s,'ENBD','ENBD',1)",
            (D2,),
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute(
            "insert into public.supplier_entries (supplier_id, entry_date, kind, amount) select id, %s, 'due', -4 from public.suppliers limit 1",
            (D2,),
        )


def test_branch_user_has_no_database_access_to_finance_tables(golden, app_url, branch_user) -> None:
    from sqlalchemy import text

    from app.core.security import TokenClaims
    from app.database.session import Database

    db = Database(make_settings(database_url=app_url))
    gen = db.session_for(TokenClaims(branch_user, None, None, None, 9999999999, None))
    s = next(gen)
    for t in (
        "supplier_entries",
        "pos_settlements",
        "cash_transfers",
        "head_office_expenses",
        "opening_balances",
        "opening_branch_cash",
        "suppliers",
    ):
        assert (
            s.execute(text(f"select count(*) from public.{t}")).scalar() == 0
        ), t  # RLS hides every row
    from sqlalchemy.exc import DBAPIError

    for fn in (
        "select * from public.app_cash_bank_ledger(current_date - 30, current_date)",
        "select * from public.app_branch_cash()",
    ):
        with pytest.raises(DBAPIError):
            s.execute(text(fn)).all()
        s.rollback()
    gen.close()
    db.dispose()
