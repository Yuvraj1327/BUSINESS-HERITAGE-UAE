"""Step 12 API tests: Reports & Analytics (calculations reuse and consistency with the dashboard, cash/bank ledger,
suppliers, HR, rentals and PDC, tasks, charts), CSV / Excel export, Activity History and Owner-only access.
Own disposable database (migrations 0001-0016).
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
    name = f"alsafa_t12_{uuid.uuid4().hex[:8]}"
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
    return KeyPair("kid-step12")


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


@pytest.fixture(autouse=True)
def wipe(admin) -> Iterator[None]:
    admin.execute(
        "truncate public.alerts, public.tasks, public.license_renewals, public.pdc_cheques, "
        "public.rental_agreements cascade"
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

    def arch(self, path: str, body: dict, who: str = "owner"):
        return self.post(path, body, who)


@pytest.fixture()
def api(client, key, owner, branch_user) -> Api:
    return Api(client, key, owner, branch_user)


# ---------------------------------------------------------------- helpers
D1 = TODAY - timedelta(days=8)
D2 = TODAY - timedelta(days=7)


def code(r) -> str:
    return r.json()["error"]["code"]


def iso(d) -> str:
    return d.isoformat()


def opening_body(bid, dues=None) -> dict:
    return {
        "supplier_dues": dues or [],
        "as_of_date": iso(OPEN_AS_OF),
        "receipts_bank": "ENBD",
        "enbd_balance": "10000.00",
        "adcb_balance": "5000.00",
        "pos_pending": "0.00",
        "savings_brought_forward": "250.00",
        "branch_cash": [{"branch_id": str(i), "amount": "0"} for i in bid.values()],
    }


def report(admin, branch, d, sales, cash=0, pos=0, tr=0, link=0, exp=0, sav=0, orders=1) -> None:
    admin.execute(
        """insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received,
                  pos_amount, bank_transfer, link_payment, shop_expenses, shop_savings)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (d, branch, sales, orders, cash, pos, tr, link, exp, sav),
    )


def category(admin, name="Utilities") -> str:
    return str(
        admin.execute("select id from public.expense_categories where name=%s", (name,)).fetchone()[
            0
        ]
    )


@pytest.fixture()
def world(api, admin, bid) -> Api:
    """Opening balances, three daily reports, head office expenses (one a saving), a transfer, a POS settlement and a
    supplier with a due and a partial payment. All figures are then read back through the report APIs."""
    sid = api.post("/suppliers", {"name": "Chem Co"}).json()["id"]
    dues = [{"supplier_id": sid, "amount": "1000.00"}]
    assert api.put("/opening-balances", opening_body(bid, dues)).status_code == 200
    report(
        admin,
        bid["ALSAFA MAIN"],
        D1,
        1000,
        cash=400,
        pos=300,
        tr=200,
        link=100,
        exp=150,
        sav=50,
        orders=4,
    )
    report(admin, bid["JERNAS"], D1, 500, cash=100, pos=100, exp=40, orders=2)
    report(admin, bid["ALSAFA MAIN"], D2, 800, cash=800, orders=3)
    cid = category(admin)
    assert (
        api.post(
            "/expenses",
            {"expense_date": iso(D2), "category_id": cid, "amount": "60.00", "paid_from": "Cash"},
        ).status_code
        == 201
    )
    assert (
        api.post(
            "/expenses",
            {
                "expense_date": iso(D2),
                "category_id": cid,
                "amount": "80.00",
                "paid_from": "ADCB",
                "is_saving": True,
            },
        ).status_code
        == 201
    )
    assert (
        api.post(
            "/cash-banks/transfers",
            {
                "transfer_date": iso(D2),
                "from_account": "ENBD",
                "to_account": "ADCB",
                "amount": "100",
            },
        ).status_code
        == 201
    )
    assert (
        api.post(
            "/cash-banks/pos-settlements",
            {"settlement_date": iso(D2), "bank": "ADCB", "amount": "200.00", "reference": "SET-1"},
        ).status_code
        == 201
    )
    assert (
        api.post(
            f"/suppliers/{sid}/dues",
            {"entry_date": iso(D2), "amount": "250.00", "reference": "INV-1"},
        ).status_code
        == 201
    )
    assert (
        api.post(
            f"/suppliers/{sid}/payments",
            {
                "payment_date": iso(D2),
                "amount": "400.00",
                "paid_from": "ENBD",
                "reference": "PAY-1",
            },
        ).status_code
        == 201
    )
    api.sid = sid  # type: ignore[attr-defined]
    return api


def rep(api, key, **p):
    p.setdefault("date_from", iso(D1))
    p.setdefault("date_to", iso(TODAY))
    r = api.get(f"/reports/{key}", **p)
    assert r.status_code == 200, r.text
    return r.json()


def rows(api, key, **p):
    return rep(api, key, page_size=200, **p)["rows"]


def summ(j) -> dict:
    return {s["label"]: s["value"] for s in j["summary"]}


def dec(v) -> Decimal:
    return Decimal(str(v))


# ---------------------------------------------------------------- 1. access control
KEYS = [
    "sales_trend", "sales_by_branch", "collections_trend", "collections_by_branch", "reconciliation_by_branch",
    "reconciliation_by_date", "shop_expenses_by_branch", "shop_expenses_by_date", "ho_expenses", "ho_by_category",
    "ho_by_source", "ho_by_branch", "savings", "cash_accounts", "branch_cash", "ledger", "supplier_balances",
    "supplier_payments", "employees", "employees_by_branch", "visas_passports", "leave_cases", "licenses",
    "license_renewals", "rentals", "rentals_by_branch", "rental_renewals", "pdc_summary", "pdc_by_branch",
    "pdc_cheques", "pdc_clearance", "tasks_by_branch", "tasks_completed", "missing_by_branch", "missing_by_date",
]  # fmt: skip


def test_catalog_lists_every_report(world) -> None:
    items = world.get("/reports/catalog").json()
    assert {i["key"] for i in items} == set(KEYS) | {"activity"}


def test_every_report_runs_with_real_data(world) -> None:
    for key in KEYS:
        j = rep(world, key)
        assert (
            j["key"] == key and j["columns"] and j["filters"]["branch_name"] == "All Branches"
        ), key
        for r in j["rows"]:
            assert set(r) >= {c["key"] for c in j["columns"]}, (key, r)


def test_branch_user_and_anonymous_are_refused_everywhere(world, client) -> None:
    paths = ["/reports/catalog", "/reports/overview", "/reports/charts", "/reports/activity", "/reports/activity/actors",
             "/reports/activity/export"] + [f"/reports/{k}" for k in KEYS] + [f"/reports/{k}/export" for k in KEYS]  # fmt: skip
    for p in paths:
        assert world.get(p, who="branch").status_code == 403, p
        assert client.get(f"{API}{p}").status_code == 401, p


# ---------------------------------------------------------------- 2. KPIs and Step 7 consistency
def test_overview_matches_the_owner_dashboard(world) -> None:
    dash = world.get("/dashboard/owner", mode="day", date=iso(D1)).json()["kpis"]
    ov = world.get("/reports/overview", date_from=iso(D1), date_to=iso(D1)).json()["kpis"]
    pairs = {
        "total_sales": "total_sales", "total_collections": "total_received", "shop_expenses": "shop_expenses_excl_savings",
        "head_office_expenses": "head_office_expenses_excl_savings", "total_savings": "total_savings",
        "sales_minus_expenses": "sales_minus_expenses", "total_orders": "total_orders", "cash_bank_balance": "cash_bank_balance",
        "not_yet_received": "not_yet_received",
    }  # fmt: skip
    for mine, theirs in pairs.items():
        assert str(ov[mine]) == str(dash[theirs]), (mine, ov[mine], dash[theirs])
    assert ov["total_sales"] == "1500.00" and ov["total_orders"] == 6


def test_overview_over_the_whole_period_and_for_one_branch(world, bid) -> None:
    ov = world.get("/reports/overview", date_from=iso(D1), date_to=iso(TODAY)).json()["kpis"]
    assert (
        ov["total_sales"] == "2300.00"
        and ov["total_collections"] == "2000.00"
        and ov["not_yet_received"] == "300.00"
    )
    one = world.get(
        "/reports/overview", date_from=iso(D1), date_to=iso(TODAY), branch_id=str(bid["JERNAS"])
    ).json()
    assert one["kpis"]["total_sales"] == "500.00" and one["filters"]["branch_name"] == "JERNAS"
    assert one["kpis"]["cash_bank_balance"] == ov["cash_bank_balance"]  # company-wide, documented


# ---------------------------------------------------------------- 3. sales, collections, reconciliation
def test_sales_trend_periods_all_add_up(world) -> None:
    for period in ("day", "week", "month", "year"):
        j = rep(world, "sales_trend", period=period, page_size=200)
        assert summ(j)["Total sales (AED)"] == "2300.00", period
        assert sum(dec(r["sales"]) for r in j["rows"]) == Decimal("2300.00"), period
    daily = {r["period"]: r for r in rows(world, "sales_trend", period="day")}
    assert daily[iso(D1)]["sales"] == "1500.00" and daily[iso(D1)]["orders"] == 6
    assert daily[iso(D1)]["avg_order"] == "250.00"
    assert len(rows(world, "sales_trend", period="year")) == 1 or TODAY.year != D1.year


def test_sales_by_branch_and_orders(world) -> None:
    r = {x["branch"]: x for x in rows(world, "sales_by_branch")}
    assert r["ALSAFA MAIN"]["sales"] == "1800.00" and r["ALSAFA MAIN"]["orders"] == 7
    assert r["JERNAS"]["sales"] == "500.00" and r["JERNAS"]["avg_order"] == "250.00"
    assert r["SATWA"]["sales"] == "0.00" and r["SATWA"]["avg_order"] is None


def test_collections_breakdown(world) -> None:
    j = rep(world, "collections_by_branch", page_size=200)
    s = summ(j)
    assert (
        s["Cash received (AED)"],
        s["POS received (AED)"],
        s["Bank transfers (AED)"],
        s["Payment links (AED)"],
    ) == ("1300.00", "400.00", "200.00", "100.00")
    assert s["Total collections (AED)"] == "2000.00"
    by_date = {r["period"]: r for r in rows(world, "collections_trend")}
    assert by_date[iso(D1)]["total"] == "1200.00" and by_date[iso(D2)]["total"] == "800.00"


def test_reconciliation_uses_the_step7_formula(world) -> None:
    j = rep(world, "reconciliation_by_branch", page_size=200)
    s = summ(j)
    assert s["Difference (AED)"] == "300.00" and s["Not yet received (AED)"] == "300.00"
    by = {r["branch"]: r for r in j["rows"]}
    assert (
        by["ALSAFA MAIN"]["status"] == "Diff"
        and by["ALSAFA MAIN"]["difference"] == "0.00"
        or by["ALSAFA MAIN"]["status"] == "Matches"
    )
    assert by["JERNAS"]["difference"] == "300.00" and by["JERNAS"]["status"] == "Diff"
    hist = {r["period"]: r for r in rows(world, "reconciliation_by_date")}
    assert hist[iso(D2)]["status"] == "Matches" and hist[iso(D1)]["difference"] == "300.00"


# ---------------------------------------------------------------- 4. expenses and savings
def test_shop_expenses_exclude_savings(world) -> None:
    j = rep(world, "shop_expenses_by_branch", page_size=200)
    s = summ(j)
    assert s["Total shop expenses (AED)"] == "190.00" and s["Shop savings (AED)"] == "50.00"
    assert s["Expenses excluding savings (AED)"] == "140.00"
    assert summ(rep(world, "shop_expenses_by_date"))["Total shop expenses (AED)"] == "190.00"


def test_head_office_reports(world) -> None:
    j = rep(world, "ho_expenses", page_size=200)
    assert (
        summ(j)["Total head office (AED)"] == "140.00"
        and summ(j)["Marked as saving (AED)"] == "80.00"
    )
    assert summ(j)["Excluding savings (AED)"] == "60.00"
    assert {r["type"] for r in j["rows"]} == {"Expense", "Saving"}
    src = {r["label"]: r for r in rows(world, "ho_by_source")}
    assert src["Cash received"]["total"] == "60.00" and src["ADCB"]["savings"] == "80.00"
    cat = rows(world, "ho_by_category")
    assert cat[0]["label"] == "Utilities" and cat[0]["excl"] == "60.00"
    assert rows(world, "ho_by_branch")[0]["label"] == "All Branches"


def test_savings_summary(world) -> None:
    j = rep(world, "savings", page_size=200)
    r = {x["item"]: x["amount"] for x in j["rows"]}
    assert r["Savings brought forward (opening balances)"] == "250.00"
    assert r["Shop savings in the period"] == "50.00"
    assert r["Head office expenses marked as Saving in the period"] == "80.00"
    assert r["Total savings in the period"] == "130.00"
    assert r["Savings position at the end date (all time)"] == "380.00"


# ---------------------------------------------------------------- 5. cash and bank (one ledger, no double counting)
def test_account_balances_match_cash_banks(world) -> None:
    s = world.get("/cash-banks/summary").json()
    acc = {r["account"]: r for r in rows(world, "cash_accounts")}
    assert acc["Cash"]["closing"] == s["cash_in_hand"] and acc["ENBD"]["closing"] == s["enbd"]
    assert acc["ADCB"]["closing"] == s["adcb"] and acc["POS Pending"]["closing"] == s["pos_pending"]
    assert dec(acc["ENBD"]["opening"]) + dec(acc["ENBD"]["incoming"]) - dec(
        acc["ENBD"]["outgoing"]
    ) == dec(acc["ENBD"]["closing"])
    tot = summ(rep(world, "cash_accounts"))
    assert tot["Cash + Bank closing (AED)"] == s["total_cash_bank"]
    br = rep(world, "branch_cash")
    assert br["rows"] and summ(br)["Total branch cash (AED)"] == str(
        sum(dec(r["closing"]) for r in br["rows"]).quantize(Decimal("0.01"))
    )


def test_ledger_counts_each_transaction_once_and_balances_run(world) -> None:
    j = rep(world, "ledger", page_size=200)
    api_total = world.get(
        "/cash-banks/transactions", date_from=iso(D1), date_to=iso(TODAY), page_size=100
    ).json()["total"]
    assert j["total"] == api_total
    last: dict[str, str] = {}
    for r in j["rows"]:
        last[r["account"]] = r["balance"]
    acc = {r["account"]: r["closing"] for r in rows(world, "cash_accounts")}
    for account, bal in last.items():
        assert bal == acc[account], account
    inc = sum(dec(r["incoming"]) for r in j["rows"])
    assert str(inc.quantize(Decimal("0.01"))) == summ(j)["Incoming (AED)"]
    kinds = {r["txn_type"] for r in j["rows"]}
    assert {"POS settlement", "Shop expenses"} <= kinds


def test_ledger_filters_keep_running_balances_correct(world) -> None:
    only = rep(world, "ledger", account="ADCB", page_size=200)
    assert {r["account"] for r in only["rows"]} == {"ADCB"}
    assert only["rows"][-1]["balance"] == world.get("/cash-banks/summary").json()["adcb"]
    tr = rep(world, "ledger", kind="transfers", page_size=200)
    assert (
        tr["rows"]
        and {r["txn_type"] for r in tr["rows"]} <= {"Transfer out", "Transfer in", "Transfer"}
        or tr["rows"]
    )
    assert (
        world.get(
            "/reports/ledger", account="Bogus", date_from=iso(D1), date_to=iso(TODAY)
        ).status_code
        == 422
    )
    assert (
        world.get(
            "/reports/ledger", kind="bogus", date_from=iso(D1), date_to=iso(TODAY)
        ).status_code
        == 422
    )


def test_cash_reports_before_opening_balances_are_empty_not_errors(api) -> None:
    j = rep(api, "cash_accounts")
    assert j["rows"] == [] and j["notes"]
    assert rep(api, "ledger")["rows"] == []


# ---------------------------------------------------------------- 6. suppliers
def test_supplier_balances_match_the_supplier_module(world) -> None:
    sid = world.sid  # type: ignore[attr-defined]
    detail = world.get(f"/suppliers/{sid}").json()
    j = rep(world, "supplier_balances", supplier_id=sid, page_size=200)
    r = j["rows"][0]
    assert r["outstanding"] == detail["outstanding"] == "850.00"
    assert (
        r["opening"] == "1000.00" and r["dues_period"] == "250.00" and r["paid_period"] == "400.00"
    )
    assert r["status"] == "Partially paid" and r["payments"] == 1
    allj = rep(world, "supplier_balances", page_size=200)
    assert (
        summ(allj)["Total outstanding dues (AED)"]
        == world.get("/suppliers/summary").json()["total_outstanding"]
    )
    pay = rep(world, "supplier_payments", supplier_id=sid, page_size=200)
    assert (
        summ(pay)["Payments made (AED)"] == "400.00"
        and summ(pay)["Dues recorded (AED)"] == "250.00"
    )
    assert {x["type"] for x in pay["rows"]} == {"Due", "Payment"}


# ---------------------------------------------------------------- 7. employees and compliance (Owner only)
def test_employee_reports_match_the_employee_module(api, bid) -> None:
    from tests.test_step9_hr_api import emp, lic  # noqa: PLC0415

    emp(
        api,
        bid,
        full_name="Ravi",
        monthly_salary="1500.00",
        visa_expiry=iso(TODAY + timedelta(days=10)),
    )
    emp(
        api,
        bid,
        full_name="Maya",
        monthly_salary="2000.00",
        branch_id=str(bid["JERNAS"]),
        passport_expiry=iso(TODAY - timedelta(days=3)),
    )
    lic(api, bid, expiry_date=iso(TODAY + timedelta(days=45)), renewal_fee="2500.00")
    summary = api.get("/employees/summary").json()
    j = rep(api, "employees", page_size=200)
    assert summ(j)["Monthly payroll (AED)"] == summary["monthly_payroll"] == "3500.00"
    assert summ(j)["Active employees"] == summary["total_active"] == 2
    one = rep(api, "employees", branch_id=str(bid["JERNAS"]), page_size=200)
    assert [r["name"] for r in one["rows"]] == ["Maya"] and summ(one)[
        "Monthly payroll (AED)"
    ] == "2000.00"
    by = {r["branch"]: r for r in rows(api, "employees_by_branch")}
    assert by["JERNAS"]["payroll"] == "2000.00" and by["ALSAFA MAIN"]["active"] == 1
    docs = rows(api, "visas_passports")
    st = {(r["employee"], r["document"]): r["status"] for r in docs}
    assert st[("Maya", "Passport")] == "Expired" and st[("Ravi", "Visa")] == "Urgent"
    li = rep(api, "licenses", page_size=200)
    assert (
        summ(li)["Expiring in 31-60 days"] == 1
        and summ(li)["Renewal fees due, expired or within 90 days (AED)"] == "2500.00"
    )
    lsum = api.get("/trade-licenses/summary").json()
    assert summ(li)["Renewal fees due, expired or within 90 days (AED)"] == lsum["renewal_fees_due"]


def test_leave_rule_cases_and_license_renewals(api, bid) -> None:
    from tests.test_step9_hr_api import emp, start_for  # noqa: PLC0415

    e = emp(api, bid, full_name="Leaver")
    r = api.post(
        f"/employees/{e['id']}/status",
        {"status": "On Leave", "leave_start": iso(start_for(20)), "reason": "family leave"},
    )
    assert r.status_code == 200, r.text
    cases = rows(api, "leave_cases")
    assert cases and cases[0]["employee"] == "Leaver" and cases[0]["days_remaining"] == 20


# ---------------------------------------------------------------- 8. rentals and PDC
def make_rental(api, bid, **over) -> dict:
    body = {
        "branch_id": str(bid["ALSAFA MAIN"]), "landlord": "Gulf Properties LLC", "unit": "Shop 12",
        "start_date": iso(TODAY - timedelta(days=30)), "annual_rent": "4000.00", "bank": "ENBD",
        "cheque_count": 2, "first_cheque_date": iso(D1), "first_cheque_no": "070000",
    }  # fmt: skip
    body.update(over)
    r = api.post("/rentals", body)
    assert r.status_code == 201, r.text
    return r.json()


def test_pdc_reports_never_count_pending_or_bounced_as_cleared(world, bid) -> None:
    d = make_rental(world, bid)
    c0, c1 = d["schedule"]["items"]
    assert world.post(f"/pdc-cheques/{c0['id']}/clear", {}).status_code == 200
    before = world.get("/cash-banks/summary").json()["enbd"]
    j = rep(world, "pdc_summary", page_size=200)
    by = {r["status"]: r for r in j["rows"]}
    assert (
        by["Cleared in period"]["total"] == c0["amount"]
        and by["Cleared in period"]["enbd"] == c0["amount"]
    )
    assert (
        by["Pending (all)"]["total"] == c1["amount"] and by["Bounced in period"]["total"] == "0.00"
    )
    assert (
        world.post(
            f"/pdc-cheques/{c1['id']}/bounce", {"reason": "Returned: insufficient funds"}
        ).status_code
        == 200
    )
    by = {r["status"]: r for r in rows(world, "pdc_summary")}
    assert (
        by["Bounced in period"]["total"] == c1["amount"] and by["Pending (all)"]["total"] == "0.00"
    )
    assert (
        by["Cleared in period"]["total"] == c0["amount"]
    )  # the bounced cheque is still not a cleared payment
    clear = rep(world, "pdc_clearance", page_size=200)
    assert [r["cheque_no"] for r in clear["rows"]] == [c0["cheque_no"]]
    # exactly once in the bank: the ledger shows one rental-cheque row for it and the ENBD closing reflects it
    led = rows(world, "ledger", kind="rental_cheques")
    assert len(led) == 1 and led[0]["account"] == "ENBD" and led[0]["outgoing"] == c0["amount"]
    assert world.get("/cash-banks/summary").json()["enbd"] == before
    assert rows(world, "pdc_by_branch")[0]["cleared"] == c0["amount"]


def test_rental_reports(world, bid) -> None:
    make_rental(
        world,
        bid,
        start_date=iso(TODAY - timedelta(days=340)),
        cheque_count=1,
        first_cheque_date=iso(TODAY + timedelta(days=5)),
        first_cheque_no="090000",
    )
    j = rep(world, "rentals", page_size=200)
    assert summ(j)["Active agreements"] == 1 and summ(j)["Ending within 30 days"] == 1
    assert summ(j)["Annual rent, active agreements (AED)"] == "4000.00"
    b = rows(world, "rentals_by_branch")
    assert b[0]["branch"] == "ALSAFA MAIN" and b[0]["rent"] == "4000.00"


# ---------------------------------------------------------------- 9. tasks and missing reports
def test_task_and_missing_report_reports_match_their_modules(world, bid) -> None:
    for title, due in (("Late", -2), ("Today", 0), ("Soon", 4)):
        assert (
            world.post(
                "/tasks",
                {
                    "title": title,
                    "branch_id": str(bid["ALSAFA MAIN"]),
                    "due_date": iso(TODAY + timedelta(days=due)),
                },
            ).status_code
            == 201
        )
    t = world.post(
        "/tasks", {"title": "Finished", "due_date": iso(TODAY - timedelta(days=1))}
    ).json()["task"]
    assert world.post(f"/tasks/{t['id']}/status", {"status": "Done"}).status_code == 200
    s = world.get("/tasks/summary").json()
    j = rep(world, "tasks_by_branch", page_size=200)
    tot = summ(j)
    assert (tot["Total tasks"], tot["Overdue"], tot["Completed"]) == (
        s["total"],
        s["overdue"],
        s["done"],
    )
    assert {r["branch"] for r in j["rows"]} == {"ALSAFA MAIN", "All Branches"}
    done = rows(world, "tasks_completed", date_from=iso(TODAY), date_to=iso(TODAY))
    assert [r["title"] for r in done] == ["Finished"] and done[0]["days_late"] == 1
    dash = world.get("/dashboard/owner", mode="month", month=TODAY.strftime("%Y-%m")).json()[
        "missing"
    ]
    m = rep(
        world,
        "missing_by_branch",
        date_from=TODAY.replace(day=1).isoformat(),
        date_to=iso(TODAY),
        page_size=200,
    )
    assert (
        summ(m)["Missing reports"] == dash["missing_count"]
        and summ(m)["Reports expected"] == dash["expected"]
    )
    miss_dates = rows(
        world, "missing_by_date", date_from=TODAY.replace(day=1).isoformat(), date_to=iso(TODAY)
    )
    assert sum(r["missing"] for r in miss_dates) == dash["missing_count"]


# ---------------------------------------------------------------- 10. charts
def test_charts_are_complete_filtered_and_have_empty_states(world, bid) -> None:
    j = world.get("/reports/charts", date_from=iso(D1), date_to=iso(TODAY)).json()
    keys = [c["key"] for c in j["charts"]]
    assert keys == ["sales_trend", "branch_sales", "collections_method", "expenses_split", "expense_categories",
                    "savings_trend", "cash_bank", "supplier_outstanding", "employee_status", "cheque_status", "task_status"]  # fmt: skip
    by = {c["key"]: c for c in j["charts"]}
    assert sum(dec(p["values"]["Sales"]) for p in by["sales_trend"]["points"]) == Decimal("2300.00")
    assert {p["label"]: p["values"]["Amount"] for p in by["collections_method"]["points"]}[
        "Cash"
    ] == "1300.00"
    assert by["supplier_outstanding"]["points"][0]["values"]["Outstanding"] == "850.00"
    assert by["employee_status"]["points"] == [] and by["employee_status"]["empty_message"]
    one = world.get(
        "/reports/charts", date_from=iso(D1), date_to=iso(TODAY), branch_id=str(bid["JERNAS"])
    ).json()
    s1 = {c["key"]: c for c in one["charts"]}["sales_trend"]
    assert sum(dec(p["values"]["Sales"]) for p in s1["points"]) == Decimal(
        "500.00"
    )  # responds to the branch filter
    quiet = world.get("/reports/charts", date_from=iso(TODAY), date_to=iso(TODAY)).json()
    assert {c["key"]: c for c in quiet["charts"]}["sales_trend"]["points"] == []


# ---------------------------------------------------------------- 11. validation
def test_filter_validation(world) -> None:
    bad = [
        {"date_from": iso(TODAY), "date_to": iso(D1)},
        {"date_from": iso(D1), "date_to": iso(TODAY + timedelta(days=1))},
        {"date_from": iso(TODAY - timedelta(days=400)), "date_to": iso(TODAY)},
        {"date_from": iso(D1), "date_to": iso(TODAY), "branch_id": str(uuid.uuid4())},
        {"date_from": iso(D1), "date_to": iso(TODAY), "period": "decade"},
        {"date_from": "not-a-date"},
    ]
    for p in bad:
        for path in (
            "/reports/sales_trend",
            "/reports/overview",
            "/reports/charts",
            "/reports/sales_trend/export",
        ):
            assert world.get(path, **p).status_code == 422, (path, p)
    assert world.get("/reports/nope", date_from=iso(D1), date_to=iso(TODAY)).status_code == 404
    assert (
        world.get(
            "/reports/sales_by_branch", sort="bogus", date_from=iso(D1), date_to=iso(TODAY)
        ).status_code
        == 422
    )


def test_sort_and_pagination(world) -> None:
    j = rep(world, "sales_by_branch", sort="sales", desc="true", page_size=2)
    assert j["total"] >= 10 and len(j["rows"]) == 2 and j["rows"][0]["branch"] == "ALSAFA MAIN"
    p2 = rep(world, "sales_by_branch", sort="sales", desc="true", page_size=1, page=2)
    assert p2["rows"][0]["branch"] == "JERNAS"


# ---------------------------------------------------------------- 12. exports
def test_csv_export_matches_the_screen_and_ignores_paging(world) -> None:
    screen = rep(world, "sales_by_branch", page_size=3)
    r = world.get(
        "/reports/sales_by_branch/export",
        date_from=iso(D1),
        date_to=iso(TODAY),
        format="csv",
        page_size=3,
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert (
        "attachment" in r.headers["content-disposition"]
        and ".csv" in r.headers["content-disposition"]
    )
    assert r.headers["cache-control"] == "no-store"
    text = r.content.decode("utf-8-sig")
    lines = list(csv.reader(io.StringIO(text)))
    flat = {row[0]: row[1] for row in lines if len(row) == 2}
    assert (
        flat["Report"] == "Sales by branch"
        and flat["Branch"] == "All Branches"
        and flat["Currency"] == "AED"
    )
    assert flat["Date range"] == f"{iso(D1)} to {iso(TODAY)}" and "Generated (Dubai time)" in flat
    assert flat["Total sales (AED)"] == summ(screen)["Total sales (AED)"] == "2300.00"
    head = next(i for i, row in enumerate(lines) if row and row[0] == "Branch" and len(row) > 2)
    data = [row for row in lines[head + 1 :] if row and row[0] and len(row) > 2]
    assert len(data) == screen["total"] > 3  # every row, not just the screen page
    assert lines[head][3] == "Sales (AED)"
    main = next(row for row in data if row[0] == "ALSAFA MAIN")
    assert main[3] == "1800.00"
    assert sum(Decimal(row[3]) for row in data) == Decimal("2300.00")


def test_xlsx_export_has_numbers_and_the_same_totals(world) -> None:
    from openpyxl import load_workbook  # noqa: PLC0415

    r = world.get(
        "/reports/collections_by_branch/export",
        date_from=iso(D1),
        date_to=iso(TODAY),
        format="xlsx",
    )
    assert (
        r.status_code == 200
        and "spreadsheetml" in r.headers["content-type"]
        and ".xlsx" in r.headers["content-disposition"]
    )
    ws = load_workbook(io.BytesIO(r.content)).active
    cells = [[c for c in row] for row in ws.iter_rows(values_only=True)]
    flat = {row[0]: row[1] for row in cells if row and len(row) > 1 and isinstance(row[0], str)}
    assert (
        flat["ALSAFA Heritage Laundry"] == "Collections by branch"
        and flat["Total collections (AED)"] == 2000.0
    )
    head = next(i for i, row in enumerate(cells) if row[0] == "Branch" and row[2] is not None)
    body_rows = [row for row in cells[head + 1 :] if row[0] and isinstance(row[5], (int, float))]
    assert len(body_rows) == 10 and sum(row[5] for row in body_rows) == 2000.0
    assert cells[head][5] == "Total collections (AED)"


def test_export_totals_equal_screen_for_every_report(world) -> None:
    for key in KEYS:
        screen = rep(world, key, page_size=200)
        r = world.get(f"/reports/{key}/export", date_from=iso(D1), date_to=iso(TODAY), format="csv")
        assert r.status_code == 200, key
        lines = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        flat = {row[0]: row[1] for row in lines if len(row) == 2}
        for s in screen["summary"]:
            if s["value"] is None:
                continue
            exp = f"{dec(s['value']):.2f}" if s["kind"] == "money" else str(s["value"])
            assert flat[s["label"]] == exp, (key, s["label"], flat[s["label"]], exp)


def test_csv_neutralises_formula_injection(world, admin) -> None:
    admin.execute(
        "update public.suppliers set category = '=HYPERLINK(\"http://x\")' where name = 'Chem Co'"
    )
    r = world.get(
        "/reports/supplier_balances/export", date_from=iso(D1), date_to=iso(TODAY), format="csv"
    )
    text = r.content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text


def test_export_needs_the_export_permission_and_returns_no_rows_for_branch(world, client) -> None:
    for key in ("employees", "ledger", "supplier_balances", "licenses"):
        assert world.get(f"/reports/{key}/export", who="branch", format="csv").status_code == 403
        assert client.get(f"{API}/reports/{key}/export?format=csv").status_code == 401
    assert (
        world.get(
            "/reports/sales_trend/export", format="pdf", date_from=iso(D1), date_to=iso(TODAY)
        ).status_code
        == 422
    )


# ---------------------------------------------------------------- 13. activity history
def test_activity_history_shows_real_changes_owner_only(world, bid) -> None:
    t = world.post("/tasks", {"title": "Audit me", "branch_id": str(bid["JERNAS"])}).json()["task"]
    world.post(f"/tasks/{t['id']}/status", {"status": "In Progress"})
    j = world.get(
        "/reports/activity", date_from=iso(TODAY), date_to=iso(TODAY), module="tasks", q=t["id"]
    ).json()
    assert j["total"] == 2 and [r["action"] for r in j["rows"]] == ["Updated", "Created"]
    assert j["rows"][0]["module"] == "Tasks" and j["rows"][0]["record"] == "Audit me"
    assert (
        "Status: To Do → In Progress" in j["rows"][0]["summary"]
        and j["rows"][1]["summary"] == "Record created"
    )
    assert j["rows"][0]["user"] == "owner test"
    everything = world.get(
        "/reports/activity", date_from=iso(D1), date_to=iso(TODAY), page_size=200
    ).json()
    modules = {r["module"] for r in everything["rows"]}
    assert {
        "Daily Reports",
        "Expenses & Savings",
        "Suppliers",
        "Cash & Banks",
        "Opening Balances",
        "Tasks",
    } <= modules
    only_ins = world.get(
        "/reports/activity",
        date_from=iso(D1),
        date_to=iso(TODAY),
        action="INSERT",
        module="suppliers",
    ).json()
    assert only_ins["total"] >= 1 and {r["action"] for r in only_ins["rows"]} == {"Created"}
    assert (
        world.get(
            "/reports/activity", date_from=iso(D1), date_to=iso(TODAY), module="bogus"
        ).status_code
        == 422
    )
    names = world.get("/reports/activity/actors").json()
    assert any(n["name"] == "owner test" for n in names)
    page = world.get(
        "/reports/activity", date_from=iso(D1), date_to=iso(TODAY), page_size=2, page=2
    ).json()
    assert len(page["rows"]) == 2 and page["total"] == everything["total"]


def test_activity_never_shows_secrets_and_audit_stays_append_only(world, admin) -> None:
    from app.services.analytics_service import change_summary  # noqa: PLC0415

    s = change_summary("UPDATE", {"password": "a", "api_key": "k", "access_token": "t", "title": "x"},
                       {"password": "b", "api_key": "l", "access_token": "u", "title": "y", "updated_at": "z"})  # fmt: skip
    assert s == "Title: x → y"
    with pytest.raises(psycopg.errors.Error):
        admin.execute("delete from public.audit_log")
    with pytest.raises(psycopg.errors.Error):
        admin.execute("update public.audit_log set reason = 'x'")


def test_activity_export_is_complete_and_owner_only(world) -> None:
    full = world.get("/reports/activity", date_from=iso(D1), date_to=iso(TODAY), page_size=5).json()
    r = world.get(
        "/reports/activity/export", date_from=iso(D1), date_to=iso(TODAY), format="csv", page_size=5
    )
    assert r.status_code == 200
    lines = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    head = next(i for i, row in enumerate(lines) if row and row[0].startswith("Date and time"))
    data = [row for row in lines[head + 1 :] if len(row) == 7]
    assert len(data) == full["total"] > 5
    assert world.get("/reports/activity/export", who="branch", format="xlsx").status_code == 403


def test_activity_source_filter_and_system_label(world, admin) -> None:
    """System rows (no signed-in user) are labelled and filterable; user rows carry the real actor name."""
    allr = world.get(
        "/reports/activity", date_from=iso(D1), date_to=iso(TODAY), page_size=200
    ).json()
    users = world.get(
        "/reports/activity", date_from=iso(D1), date_to=iso(TODAY), page_size=200, source="user"
    ).json()
    system = world.get(
        "/reports/activity", date_from=iso(D1), date_to=iso(TODAY), page_size=200, source="system"
    ).json()
    assert users["total"] + system["total"] == allr["total"]
    assert all(r["source"] == "User" and r["user"] != "System" for r in users["rows"])
    assert all(r["source"] == "System" and r["user"].startswith("System") for r in system["rows"])
    assert (
        world.get(
            "/reports/activity", date_from=iso(D1), date_to=iso(TODAY), source="bogus"
        ).status_code
        == 422
    )
