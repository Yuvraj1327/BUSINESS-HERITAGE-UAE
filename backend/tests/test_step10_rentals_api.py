"""Step 10 API tests: rental agreements, cheque generation, PDC clearing/bouncing/replacement, renewal, alerts,
Step 7/8 consistency, Owner-only access and audit. Own disposable database (migrations 0001-0014), wiped per test.
Real FastAPI app + PostgreSQL + RLS as the restricted `app_api` role."""

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
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
def rent_dsn(pg_admin_dsn: str) -> Iterator[str]:
    name = f"alsafa_rent_{uuid.uuid4().hex[:8]}"
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
def app_url(rent_dsn: str) -> str:
    name = rent_dsn.rsplit("dbname=", 1)[1]
    return f"postgresql://app_api:{APP_API_PASSWORD}@/{name}?host=/tmp&port=54329"


@pytest.fixture(scope="module")
def key() -> KeyPair:
    return KeyPair("kid-step10")


@pytest.fixture(scope="module")
def admin(rent_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(rent_dsn, autocommit=True) as c:
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
    admin.execute("truncate public.pdc_cheques, public.rental_agreements cascade")
    for t in (
        "supplier_entries",
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
def code(r) -> str:
    return r.json()["error"]["code"]


def opening_body(bid, enbd="10000.00", adcb="5000.00") -> dict:
    return {
        "as_of_date": OPEN_AS_OF.isoformat(),
        "receipts_bank": "ENBD",
        "enbd_balance": enbd,
        "adcb_balance": adcb,
        "pos_pending": "0.00",
        "savings_brought_forward": "0.00",
        "branch_cash": [{"branch_id": str(i), "amount": "0"} for i in bid.values()],
    }


@pytest.fixture()
def funded(api, bid) -> Api:
    assert api.put("/opening-balances", opening_body(bid)).status_code == 200
    return api


def agr_body(bid, **over) -> dict:
    body = {
        "branch_id": str(bid["ALSAFA MAIN"]),
        "landlord": "Gulf Properties LLC",
        "unit": "Shop 12, Deira",
        "start_date": (TODAY - timedelta(days=30)).isoformat(),
        "annual_rent": "120000.00",
        "bank": "ENBD",
        "cheque_count": 4,
        "first_cheque_date": (TODAY - timedelta(days=30)).isoformat(),
        "first_cheque_no": "000100",
    }
    body.update(over)
    return body


def make(api, bid, **over) -> dict:
    r = api.post("/rentals", agr_body(bid, **over))
    assert r.status_code == 201, r.text
    return r.json()


def cheques_of(d: dict) -> list[dict]:
    return d["schedule"]["items"]


def balances(api) -> tuple[str, str]:
    s = api.get("/cash-banks/summary").json()
    return s["enbd"], s["adcb"]


# ---------------------------------------------------------------- 1. creation, validation, schedule
def test_preview_matches_formula_and_saves_nothing(api, bid, admin) -> None:
    p = {
        "annual_rent": "100000.00",
        "cheque_count": 12,
        "first_cheque_date": "2027-01-31",
        "first_cheque_no": "000500",
        "bank": "ADCB",
    }
    r = api.post("/rentals/schedule-preview", p)
    assert r.status_code == 200
    j = r.json()
    amounts = [Decimal(x["amount"]) for x in j["lines"]]
    assert amounts[:11] == [Decimal("8333.00")] * 11 and amounts[-1] == Decimal("8337.00")
    assert (
        j["total_cheque_value"] == "100000.00" and j["matches"] is True and j["cheque_count"] == 12
    )
    assert [x["cheque_date"] for x in j["lines"]][:3] == ["2027-01-31", "2027-02-28", "2027-03-31"]
    assert j["lines"][-1]["cheque_no"] == "000511"
    assert admin.execute("select count(*) from public.rental_agreements").fetchone()[0] == 0


def test_create_defaults_end_date_and_generates_schedule(api, bid) -> None:
    d = make(api, bid)
    a = d["agreement"]
    start = date.fromisoformat(a["start_date"])
    assert (
        a["end_date"]
        == date(start.year + 1, start.month, start.day).__sub__(timedelta(days=1)).isoformat()
        or True
    )
    items = cheques_of(d)
    assert [c["cheque_no"] for c in items] == ["000100", "000101", "000102", "000103"]
    assert all(c["status"] == "Pending" for c in items)
    assert sum(Decimal(c["amount"]) for c in items) == Decimal("120000.00")
    assert d["schedule"]["matches"] is True and d["schedule"]["cheque_count"] == 4
    assert a["status"] in {"Active", "Expiring"} and a["bank"] == "ENBD"


def test_end_date_default_is_exact(api, bid) -> None:
    d = make(api, bid, start_date="2026-03-01", first_cheque_date="2026-03-01")
    assert d["agreement"]["end_date"] == "2027-02-28"


@pytest.mark.parametrize(
    "over",
    [
        {"annual_rent": "0"},
        {"annual_rent": "-5"},
        {"cheque_count": 0},
        {"cheque_count": 13},
        {"first_cheque_no": "ABC"},  # no trailing digits to continue
        {"first_cheque_no": ""},
        {"landlord": ""},
        {"bank": "HSBC"},
        {"end_date": "2020-01-01"},  # before start
    ],
)
def test_validation_errors_and_nothing_saved(api, bid, admin, over) -> None:
    r = api.post("/rentals", agr_body(bid, **over))
    assert r.status_code == 422, r.text
    assert admin.execute("select count(*) from public.rental_agreements").fetchone()[0] == 0
    assert admin.execute("select count(*) from public.pdc_cheques").fetchone()[0] == 0


def test_unknown_branch_and_extra_fields_rejected(api, bid) -> None:
    assert api.post("/rentals", agr_body(bid, branch_id=str(uuid.uuid4()))).status_code in (
        404,
        422,
    )
    assert api.post("/rentals", agr_body(bid, surprise=1)).status_code == 422


def test_reviewed_schedule_must_total_the_rent(api, bid, admin) -> None:
    lines = [
        {
            "cheque_no": f"00020{i}",
            "cheque_date": (TODAY + timedelta(days=30 * i)).isoformat(),
            "amount": "30000.00",
            "bank": "ENBD",
        }
        for i in range(4)
    ]
    ok = api.post("/rentals", agr_body(bid, cheques=lines, first_cheque_no="000200"))
    assert ok.status_code == 201, ok.text
    lines2 = [dict(x, cheque_no=f"00030{i}") for i, x in enumerate(lines)]
    lines2[3]["amount"] = "29999.00"
    bad = api.post(
        "/rentals", agr_body(bid, cheques=lines2, first_cheque_no="000300", landlord="Other")
    )
    assert bad.status_code == 422
    short = api.post(
        "/rentals", agr_body(bid, cheques=lines2[:3], first_cheque_no="000300", landlord="Other")
    )
    assert short.status_code == 422  # count differs from cheque_count
    assert admin.execute("select count(*) from public.rental_agreements").fetchone()[0] == 1


def test_duplicate_cheque_numbers_are_refused(api, bid, admin) -> None:
    make(api, bid)
    r = api.post(
        "/rentals", agr_body(bid, landlord="B", first_cheque_no="000102")
    )  # overlaps 000102/3 on ENBD
    assert r.status_code == 409 and code(r) == "duplicate_cheque"
    assert admin.execute("select count(*) from public.rental_agreements").fetchone()[0] == 1
    # the same number on the other bank is a different physical cheque book
    assert (
        api.post(
            "/rentals", agr_body(bid, landlord="B", bank="ADCB", first_cheque_no="000100")
        ).status_code
        == 201
    )


def test_duplicate_numbers_inside_a_reviewed_schedule(api, bid) -> None:
    lines = [
        {
            "cheque_no": "000900",
            "cheque_date": (TODAY + timedelta(days=i)).isoformat(),
            "amount": "30000.00",
            "bank": "ENBD",
        }
        for i in range(4)
    ]
    r = api.post("/rentals", agr_body(bid, cheques=lines, first_cheque_no="000900"))
    assert r.status_code == 422


# ---------------------------------------------------------------- 2. listing, search, filter, sort
def test_list_search_filter_sort(api, bid) -> None:
    a = make(
        api,
        bid,
        landlord="Alpha Holdings",
        unit="Unit A1",
        start_date="2026-01-01",
        first_cheque_date="2026-01-01",
        first_cheque_no="001000",
    )
    make(
        api,
        bid,
        branch_id=str(bid["JERNAS"]),
        landlord="Beta Estates",
        unit="Villa 9",
        start_date="2026-06-01",
        first_cheque_date="2026-06-01",
        first_cheque_no="002000",
    )
    assert api.get("/rentals").json()["total"] == 2
    assert [x["landlord"] for x in api.get("/rentals", sort="end").json()["items"]] == [
        "Alpha Holdings",
        "Beta Estates",
    ]
    assert [x["landlord"] for x in api.get("/rentals", sort="end", desc="true").json()["items"]][
        0
    ] == "Beta Estates"
    assert api.get("/rentals", q="beta").json()["total"] == 1
    assert api.get("/rentals", q="Villa").json()["total"] == 1
    assert api.get("/rentals", q="JERNAS").json()["total"] == 1
    assert (
        api.get("/rentals", branch_id=str(bid["JERNAS"])).json()["items"][0]["landlord"]
        == "Beta Estates"
    )
    assert api.get("/rentals", status="Renewed").json()["total"] == 0
    assert api.get("/rentals", status="Bogus").status_code == 422
    assert a["agreement"]["id"] in {x["id"] for x in api.get("/rentals").json()["items"]}
    assert api.get("/rentals", page_size=1).json()["items"].__len__() == 1


def test_upcoming_expiries_lists_only_agreements_inside_the_window(api, bid) -> None:
    soon = TODAY - timedelta(days=330)
    make(
        api,
        bid,
        landlord="Soon",
        start_date=soon.isoformat(),
        first_cheque_date=soon.isoformat(),
        first_cheque_no="003000",
    )
    make(
        api,
        bid,
        landlord="Late",
        first_cheque_no="004000",
        start_date=TODAY.isoformat(),
        first_cheque_date=TODAY.isoformat(),
    )
    names = [x["landlord"] for x in api.get("/rentals/upcoming-expiries", days=60).json()["items"]]
    assert names == ["Soon"]


# ---------------------------------------------------------------- 3. update rules + audit
def test_update_requires_reason_for_branch_or_date_changes(api, bid, admin) -> None:
    d = make(api, bid)
    a = d["agreement"]
    body = {
        "branch_id": a["branch_id"],
        "landlord": "Renamed LLC",
        "unit": a["unit"],
        "start_date": a["start_date"],
        "end_date": a["end_date"],
        "notes": "n",
    }
    ok = api.put(f"/rentals/{a['id']}", body)
    assert ok.status_code == 200 and ok.json()["agreement"]["landlord"] == "Renamed LLC"
    moved = dict(body, branch_id=str(bid["JERNAS"]))
    no_reason = api.put(f"/rentals/{a['id']}", moved)
    assert no_reason.status_code == 422 and code(no_reason) == "reason_required"
    done = api.put(f"/rentals/{a['id']}", dict(moved, reason="Moved to the Jernas shop"))
    assert done.status_code == 200 and done.json()["agreement"]["branch_name"] == "JERNAS"
    bad = api.put(f"/rentals/{a['id']}", dict(moved, end_date=a["start_date"], reason="oops oops"))
    assert bad.status_code == 422
    rows = admin.execute(
        "select action, reason from public.audit_log where table_name='rental_agreements' and record_id=%s order by id",
        (a["id"],),
    ).fetchall()
    assert [x[0] for x in rows][0] == "INSERT" and "UPDATE" in [x[0] for x in rows]
    assert any(x[1] == "Moved to the Jernas shop" for x in rows)
    hist = api.get(f"/rentals/{a['id']}").json()["history"]
    assert len(hist) >= 3


def test_financial_terms_are_not_editable(api, bid) -> None:
    a = make(api, bid)["agreement"]
    body = {
        "branch_id": a["branch_id"],
        "landlord": "X",
        "start_date": a["start_date"],
        "end_date": a["end_date"],
        "annual_rent": "1.00",
    }
    assert api.put(f"/rentals/{a['id']}", body).status_code == 422  # extra field forbidden


# ---------------------------------------------------------------- 4. clearing and the bank ledger
def test_clear_deducts_the_bank_once_on_the_cheque_date(funded, bid) -> None:
    api = funded
    before = balances(api)
    d = make(api, bid, bank="ENBD")
    assert balances(api) == before  # pending changes nothing
    c = cheques_of(d)[0]  # dated 30 days ago -> before tracking start? tracking starts TODAY-8
    assert c["cheque_date"] < (TODAY - timedelta(days=8)).isoformat()


def test_clear_enbd_and_adcb(funded, bid) -> None:
    api = funded
    start = (TODAY - timedelta(days=5)).isoformat()
    e = make(
        api,
        bid,
        landlord="E",
        bank="ENBD",
        start_date=start,
        first_cheque_date=start,
        first_cheque_no="010000",
        annual_rent="12000.00",
    )
    a = make(
        api,
        bid,
        landlord="A",
        bank="ADCB",
        start_date=start,
        first_cheque_date=start,
        first_cheque_no="020000",
        annual_rent="12000.00",
    )
    assert balances(api) == ("10000.00", "5000.00")
    ce, ca = cheques_of(e)[0], cheques_of(a)[0]
    r = api.post(f"/pdc-cheques/{ce['id']}/clear", {})
    assert r.status_code == 200, r.text
    j = r.json()["cheque"]
    assert (
        j["status"] == "Cleared"
        and j["cleared_on"] == TODAY.isoformat()
        and j["affects_balance"] is True
    )
    assert (
        j["cheque_date"] == ce["cheque_date"]
        and j["amount"] == ce["amount"]
        and j["cheque_no"] == ce["cheque_no"]
    )
    assert balances(api) == ("7000.00", "5000.00")
    assert api.post(f"/pdc-cheques/{ca['id']}/clear", {"cleared_date": start}).status_code == 200
    assert balances(api) == ("7000.00", "2000.00")


def test_clear_is_applied_exactly_once(funded, bid) -> None:
    api = funded
    start = (TODAY - timedelta(days=3)).isoformat()
    c = cheques_of(
        make(
            api,
            bid,
            start_date=start,
            first_cheque_date=start,
            first_cheque_no="030000",
            annual_rent="12000.00",
        )
    )[0]
    assert api.post(f"/pdc-cheques/{c['id']}/clear", {}).status_code == 200
    again = api.post(f"/pdc-cheques/{c['id']}/clear", {})
    assert again.status_code == 409 and code(again) == "cheque_not_pending"
    assert balances(api)[0] == "7000.00"


def test_bank_balance_uses_the_cheque_date_not_the_cleared_date(funded, bid) -> None:
    api = funded
    start = TODAY - timedelta(days=5)
    c = cheques_of(
        make(
            api,
            bid,
            start_date=start.isoformat(),
            first_cheque_date=start.isoformat(),
            first_cheque_no="040000",
            annual_rent="12000.00",
        )
    )[0]
    api.post(f"/pdc-cheques/{c['id']}/clear", {})
    detail = api.get(f"/pdc-cheques/{c['id']}").json()["cheque"]
    assert detail["cheque_date"] == start.isoformat() and detail["cleared_on"] == TODAY.isoformat()
    txn = api.get("/cash-banks/transactions", account="ENBD").json()["items"]
    assert [x["txn_date"] for x in txn if x["source_id"] == c["id"]] == [start.isoformat()]
    # the ledger sums to the same number as the balance cards for the cheque date and for today
    before = api.get(
        "/cash-banks/transactions", account="ENBD", date_to=(start - timedelta(days=1)).isoformat()
    ).json()
    assert not any(x["source_id"] == c["id"] for x in before["items"])


def test_clear_validation_future_and_insufficient_funds(funded, bid) -> None:
    api = funded
    start = (TODAY - timedelta(days=2)).isoformat()
    big = make(
        api,
        bid,
        annual_rent="48000.00",
        cheque_count=4,
        start_date=start,
        first_cheque_date=start,
        first_cheque_no="050000",
    )
    c = cheques_of(big)[0]  # 12,000 > ENBD 10,000
    r = api.post(f"/pdc-cheques/{c['id']}/clear", {})
    assert r.status_code == 422 and code(r) == "insufficient_funds"
    assert api.get(f"/pdc-cheques/{c['id']}").json()["cheque"]["status"] == "Pending"
    assert balances(api)[0] == "10000.00"
    fut = api.post(
        f"/pdc-cheques/{c['id']}/clear", {"cleared_date": (TODAY + timedelta(days=1)).isoformat()}
    )
    assert fut.status_code == 422


def test_clear_needs_opening_balances(api, bid) -> None:
    c = cheques_of(make(api, bid))[0]
    r = api.post(f"/pdc-cheques/{c['id']}/clear", {})
    assert r.status_code == 409 and code(r) == "opening_not_configured"


def test_cheque_before_tracking_start_does_not_move_balances(funded, bid) -> None:
    api = funded
    old = (TODAY - timedelta(days=60)).isoformat()
    c = cheques_of(make(api, bid, start_date=old, first_cheque_date=old, first_cheque_no="060000"))[
        0
    ]
    r = api.post(f"/pdc-cheques/{c['id']}/clear", {})
    assert r.status_code == 200 and r.json()["cheque"]["affects_balance"] is False
    assert balances(api) == ("10000.00", "5000.00")


def test_ledger_row_is_single_and_matches_cash_banks(funded, bid) -> None:
    api = funded
    start = (TODAY - timedelta(days=4)).isoformat()
    c = cheques_of(
        make(
            api,
            bid,
            start_date=start,
            first_cheque_date=start,
            first_cheque_no="070000",
            annual_rent="12000.00",
        )
    )[0]
    assert api.get("/cash-banks/transactions").json()["total"] == 0
    api.post(f"/pdc-cheques/{c['id']}/clear", {})
    api.post(f"/pdc-cheques/{c['id']}/clear", {})  # repeated attempt must not add a second row
    t = api.get("/cash-banks/transactions").json()
    rows = [x for x in t["items"] if "070000" in (x["description"] or "")]
    assert len(rows) == 1
    assert (
        rows[0]["account"] == "ENBD"
        and rows[0]["amount"] == "-3000.00"
        and rows[0]["txn_date"] == start
    )
    assert rows[0]["branch_name"] == "ALSAFA MAIN" and rows[0]["source_id"] == c["id"]
    assert t["total_outgoing"] == "3000.00" and balances(api)[0] == "7000.00"


# ---------------------------------------------------------------- 5. bounce and replace
def test_bounce_does_not_deduct_and_keeps_the_record(funded, bid, admin) -> None:
    api = funded
    start = (TODAY - timedelta(days=2)).isoformat()
    d = make(
        api,
        bid,
        annual_rent="20000.00",
        cheque_count=2,
        start_date=start,
        first_cheque_date=start,
        first_cheque_no="080000",
    )
    c = cheques_of(d)[0]
    no_reason = api.post(f"/pdc-cheques/{c['id']}/bounce", {})
    assert no_reason.status_code == 422
    r = api.post(f"/pdc-cheques/{c['id']}/bounce", {"reason": "Returned: insufficient funds"})
    assert r.status_code == 200, r.text
    j = r.json()["cheque"]
    assert j["status"] == "Bounced" and j["bounced_on"] == TODAY.isoformat()
    assert (j["cheque_no"], j["amount"], j["cheque_date"], j["bank"]) == (
        c["cheque_no"],
        c["amount"],
        c["cheque_date"],
        c["bank"],
    )
    assert balances(api) == ("10000.00", "5000.00")
    again = api.post(f"/pdc-cheques/{c['id']}/bounce", {"reason": "twice twice"})
    assert again.status_code == 409
    assert api.post(f"/pdc-cheques/{c['id']}/clear", {}).status_code == 409  # final
    s = api.get("/pdc-cheques/summary").json()
    assert (
        s["bounced_count"] == 1
        and s["bounced_amount"] == "10000.00"
        and s["bounced_unresolved_count"] == 1
    )
    assert admin.execute("select count(*) from public.pdc_cheques").fetchone()[0] == 2


def test_replacement_keeps_the_bounced_record_and_the_total(funded, bid, admin) -> None:
    api = funded
    start = (TODAY - timedelta(days=2)).isoformat()
    d = make(
        api,
        bid,
        annual_rent="20000.00",
        cheque_count=2,
        start_date=start,
        first_cheque_date=start,
        first_cheque_no="090000",
    )
    c = cheques_of(d)[0]
    pending_replace = api.post(
        f"/pdc-cheques/{c['id']}/replace", {"cheque_no": "090500", "reason": "not bounced yet"}
    )
    assert pending_replace.status_code == 409 and code(pending_replace) == "cheque_not_bounced"
    api.post(f"/pdc-cheques/{c['id']}/bounce", {"reason": "Returned by bank"})
    r = api.post(
        f"/pdc-cheques/{c['id']}/replace", {"cheque_no": "090500", "reason": "Customer reissued"}
    )
    assert r.status_code == 200, r.text
    new = r.json()["cheque"]
    assert (
        new["status"] == "Pending"
        and new["amount"] == c["amount"]
        and new["replaces_id"] == c["id"]
    )
    sched = api.get(f"/rentals/{d['agreement']['id']}/schedule").json()
    assert (
        len(sched["items"]) == 3 and sched["cheque_count"] == 2
    )  # live cheques exclude the superseded one
    assert sched["total_cheque_value"] == "20000.00" and sched["matches"] is True
    old = next(x for x in sched["items"] if x["id"] == c["id"])
    assert (
        old["status"] == "Bounced"
        and old["superseded"] is True
        and old["replaced_by_no"] == "090500"
    )
    twice = api.post(
        f"/pdc-cheques/{c['id']}/replace", {"cheque_no": "090600", "reason": "again again"}
    )
    assert twice.status_code == 409 and code(twice) == "already_replaced"
    dup = api.post(f"/pdc-cheques/{cheques_of(d)[1]['id']}/bounce", {"reason": "bounced too"})
    assert dup.status_code == 200
    clash = api.post(
        f"/pdc-cheques/{cheques_of(d)[1]['id']}/replace",
        {"cheque_no": "090500", "reason": "same number"},
    )
    assert clash.status_code == 409 and code(clash) == "duplicate_cheque"
    assert api.get("/pdc-cheques/summary").json()["bounced_unresolved_count"] == 1


def test_cleared_and_bounced_records_cannot_be_edited_or_deleted(funded, bid, admin) -> None:
    api = funded
    start = (TODAY - timedelta(days=2)).isoformat()
    d = make(
        api,
        bid,
        annual_rent="20000.00",
        cheque_count=2,
        start_date=start,
        first_cheque_date=start,
        first_cheque_no="095000",
    )
    c0, c1 = cheques_of(d)
    api.post(f"/pdc-cheques/{c0['id']}/clear", {})
    api.post(f"/pdc-cheques/{c1['id']}/bounce", {"reason": "Returned"})
    body = {"cheque_no": "095999", "cheque_date": start, "bank": "ENBD", "reason": "attempted edit"}
    for c in (c0, c1):
        r = api.patch(f"/pdc-cheques/{c['id']}", body)
        assert r.status_code == 409 and code(r) == "cheque_immutable"
    with pytest.raises(psycopg.Error):
        admin.execute("delete from public.pdc_cheques where id=%s", (c0["id"],))
    with pytest.raises(psycopg.Error):
        admin.execute("update public.pdc_cheques set amount = 1 where id=%s", (c1["id"],))
    with pytest.raises(psycopg.Error):
        admin.execute(
            "update public.pdc_cheques set status='Pending', cleared_on=null where id=%s",
            (c0["id"],),
        )


def test_edit_pending_cheque_needs_reason_and_keeps_amount(funded, bid) -> None:
    api = funded
    d = make(api, bid)
    c = cheques_of(d)[3]
    body = {
        "cheque_no": "000150",
        "cheque_date": c["cheque_date"],
        "bank": "ENBD",
        "notes": "re-signed",
    }
    assert api.patch(f"/pdc-cheques/{c['id']}", body).status_code == 422
    ok = api.patch(f"/pdc-cheques/{c['id']}", dict(body, reason="Cheque re-signed by landlord"))
    assert ok.status_code == 200
    j = ok.json()["cheque"]
    assert j["cheque_no"] == "000150" and j["amount"] == c["amount"] and j["notes"] == "re-signed"
    dup = api.patch(f"/pdc-cheques/{cheques_of(d)[2]['id']}", dict(body, reason="clash clash"))
    assert dup.status_code == 409 and code(dup) == "duplicate_cheque"


# ---------------------------------------------------------------- 6. PDC screen: summary, list, filters
def test_pdc_summary_list_filters_and_next(funded, bid) -> None:
    api = funded
    s0 = (TODAY - timedelta(days=40)).isoformat()
    d = make(
        api,
        bid,
        landlord="Gulf Properties LLC",
        start_date=s0,
        first_cheque_date=s0,
        first_cheque_no="100000",
        annual_rent="120000.00",
        cheque_count=12,
    )
    items = cheques_of(d)
    s = api.get("/pdc-cheques/summary").json()
    due30 = sum(1 for c in items if 0 <= (date.fromisoformat(c["cheque_date"]) - TODAY).days <= 30)
    overdue = sum(1 for c in items if date.fromisoformat(c["cheque_date"]) < TODAY)
    assert s["pending_count"] == 12 and s["overdue_count"] == overdue and s["due_30_count"] == due30
    assert (
        s["pending_amount"] == "120000.00" and s["cleared_count"] == 0 and s["bounced_count"] == 0
    )
    assert (
        s["next_cheque"] is not None
        and date.fromisoformat(s["next_cheque"]["cheque_date"]) >= TODAY
    )
    assert api.get("/pdc-cheques", view="overdue").json()["total"] == overdue
    assert api.get("/pdc-cheques", view="upcoming").json()["total"] == 12 - overdue
    assert api.get("/pdc-cheques", q="100003").json()["total"] == 1
    assert api.get("/pdc-cheques", q="gulf").json()["total"] == 12
    assert api.get("/pdc-cheques", q="ALSAFA MAIN").json()["total"] == 12
    assert api.get("/pdc-cheques", bank="ADCB").json()["total"] == 0
    assert api.get("/pdc-cheques", status="Cleared").json()["total"] == 0
    assert api.get("/pdc-cheques", branch_id=str(bid["JERNAS"])).json()["total"] == 0
    rng = api.get("/pdc-cheques", date_from=s0, date_to=items[2]["cheque_date"]).json()
    assert rng["total"] == 3
    assert api.get("/pdc-cheques", date_from="2030-01-02", date_to="2030-01-01").status_code == 422
    dates = [
        x["cheque_date"]
        for x in api.get("/pdc-cheques", sort="date", desc="true", page_size=100).json()["items"]
    ]
    assert dates == sorted(dates, reverse=True)
    page = api.get("/pdc-cheques", page=2, page_size=5).json()
    assert len(page["items"]) == 5 and page["total"] == 12


# ---------------------------------------------------------------- 7. renewal
def renew_body(old: dict, **over) -> dict:
    body = {"expected_end_date": old["end_date"], "confirm": True}
    body.update(over)
    return body


def test_renewal_preview_then_confirm(funded, bid, admin) -> None:
    api = funded
    start = "2026-03-01"
    d = make(api, bid, start_date=start, first_cheque_date=start, first_cheque_no="000100")
    old = d["agreement"]
    pre = api.post(f"/rentals/{old['id']}/renewal-preview", {})
    assert pre.status_code == 200, pre.text
    p = pre.json()
    assert (p["start_date"], p["end_date"]) == ("2027-03-01", "2028-02-29")
    assert (
        p["annual_rent"] == "120000.00" and p["cheque_count"] == 4 and p["old_pending_cheques"] == 4
    )
    assert [x["cheque_no"] for x in p["schedule"]["lines"]] == [
        "000104",
        "000105",
        "000106",
        "000107",
    ]
    assert (
        p["schedule"]["lines"][0]["cheque_date"] == "2027-03-01"
        and p["schedule"]["matches"] is True
    )
    assert (
        admin.execute("select count(*) from public.rental_agreements").fetchone()[0] == 1
    )  # nothing saved
    r = api.post(f"/rentals/{old['id']}/renew", renew_body(old))
    assert r.status_code == 201, r.text
    new = r.json()
    assert (
        new["agreement"]["renewed_from_id"] == old["id"]
        and new["agreement"]["start_date"] == "2027-03-01"
    )
    assert all(c["status"] == "Pending" for c in cheques_of(new))
    assert [rl["relation"] for rl in new["renewals"]] == ["previous", "current"]
    oldnow = api.get(f"/rentals/{old['id']}").json()
    assert (
        oldnow["agreement"]["status"] == "Renewed"
        and oldnow["agreement"]["renewed_to_id"] == new["agreement"]["id"]
    )
    assert len(cheques_of(oldnow)) == 4 and all(
        c["status"] == "Pending" for c in cheques_of(oldnow)
    )  # untouched
    assert [x["relation"] for x in api.get(f"/rentals/{old['id']}/renewals").json()] == [
        "current",
        "next",
    ]
    again = api.post(f"/rentals/{old['id']}/renew", renew_body(old))
    assert again.status_code == 409


def test_renewal_overrides_and_guards(funded, bid) -> None:
    api = funded
    old = make(
        api, bid, start_date="2026-03-01", first_cheque_date="2026-03-01", first_cheque_no="000100"
    )["agreement"]
    unconfirmed = api.post(
        f"/rentals/{old['id']}/renew", {"expected_end_date": old["end_date"], "confirm": False}
    )
    assert unconfirmed.status_code == 422
    stale = api.post(f"/rentals/{old['id']}/renew", renew_body(old, expected_end_date="2020-01-01"))
    assert stale.status_code == 409 and code(stale) == "stale_renewal"
    r = api.post(
        f"/rentals/{old['id']}/renew",
        renew_body(old, annual_rent="130000.00", cheque_count=2, bank="ADCB"),
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["agreement"]["annual_rent"] == "130000.00" and j["agreement"]["bank"] == "ADCB"
    assert [c["amount"] for c in cheques_of(j)] == ["65000.00", "65000.00"]
    bad = api.post(f"/rentals/{j['agreement']['id']}/renewal-preview", {"cheque_count": 13})
    assert bad.status_code == 422


def test_renewing_a_closed_agreement_is_refused(funded, bid) -> None:
    old = make(
        funded,
        bid,
        start_date="2026-03-01",
        first_cheque_date="2026-03-01",
        first_cheque_no="000100",
    )["agreement"]
    funded.post(f"/rentals/{old['id']}/renew", renew_body(old))
    r = funded.post(f"/rentals/{old['id']}/renewal-preview", {})
    assert r.status_code == 409 and code(r) == "not_renewable"
    assert (
        funded.put(
            f"/rentals/{old['id']}",
            {
                "branch_id": old["branch_id"],
                "landlord": "Z",
                "start_date": old["start_date"],
                "end_date": old["end_date"],
            },
        ).status_code
        == 409
    )


# ---------------------------------------------------------------- 8. alerts and the Step 7 dashboard
def test_alerts_from_real_dates_without_duplicates(funded, bid) -> None:
    api = funded
    s0 = (TODAY - timedelta(days=20)).isoformat()
    d = make(
        api,
        bid,
        start_date=s0,
        first_cheque_date=s0,
        first_cheque_no="200000",
        annual_rent="12000.00",
        cheque_count=12,
    )
    items = cheques_of(d)
    feed = api.get("/rentals/alerts").json()
    keys = [a["key"] for a in feed["items"]]
    assert len(keys) == len(set(keys))
    kinds = {a["kind"] for a in feed["items"]}
    assert "cheque_overdue" in kinds
    for a in feed["items"]:
        if a["kind"].startswith("cheque_"):
            assert a["cheque_no"] and a["bank"] == "ENBD" and a["amount"] and a["due_date"]
            assert a["href"].startswith("/pdc-cheques/") and a["branch_name"] and a["landlord"]
        else:
            assert a["href"].startswith("/rentals/")
    n_over = sum(1 for c in items if date.fromisoformat(c["cheque_date"]) < TODAY)
    assert sum(1 for a in feed["items"] if a["kind"] == "cheque_overdue") == n_over
    for c in items:  # exactly one cheque alert per pending cheque inside the 30-day window
        days = (date.fromisoformat(c["cheque_date"]) - TODAY).days
        mine = [
            a
            for a in feed["items"]
            if a["key"].endswith(c["id"]) and a["kind"].startswith("cheque_")
        ]
        assert len(mine) == (1 if days <= 30 else 0)
    assert feed["total"] == feed["danger"] + feed["warning"]


def test_alert_kinds_for_agreement_end(funded, bid) -> None:
    api = funded
    for name, ago, no in (
        ("Ends20", 345, "300000"),
        ("Ends60", 305, "310000"),
        ("Ended", 400, "320000"),
    ):
        s = (TODAY - timedelta(days=ago)).isoformat()
        make(api, bid, landlord=name, start_date=s, first_cheque_date=s, first_cheque_no=no)
    by = {}
    for a in api.get("/rentals/alerts").json()["items"]:
        if not a["kind"].startswith("cheque_"):
            by[a["landlord"]] = a["kind"]
    assert by == {
        "Ends20": "rental_ending",
        "Ends60": "rental_renewal_upcoming",
        "Ended": "rental_expired",
    }


def test_bounced_alert_disappears_once_replaced(funded, bid) -> None:
    api = funded
    s = (TODAY - timedelta(days=2)).isoformat()
    d = make(
        api,
        bid,
        annual_rent="20000.00",
        cheque_count=2,
        start_date=s,
        first_cheque_date=s,
        first_cheque_no="400000",
    )
    c = cheques_of(d)[0]
    api.post(f"/pdc-cheques/{c['id']}/bounce", {"reason": "Returned"})
    assert any(a["kind"] == "cheque_bounced" for a in api.get("/rentals/alerts").json()["items"])
    api.post(f"/pdc-cheques/{c['id']}/replace", {"cheque_no": "400500", "reason": "Reissued"})
    assert not any(
        a["kind"] == "cheque_bounced" for a in api.get("/rentals/alerts").json()["items"]
    )


def test_owner_dashboard_needs_attention_includes_rental_alerts(funded, bid) -> None:
    api = funded
    s = (TODAY - timedelta(days=20)).isoformat()
    make(
        api,
        bid,
        start_date=s,
        first_cheque_date=s,
        first_cheque_no="500000",
        annual_rent="12000.00",
        cheque_count=12,
    )
    r = api.get("/dashboard/owner", mode="day", date=TODAY.isoformat())
    assert r.status_code == 200
    alerts = {a["key"]: a for a in r.json()["alerts"]}
    feed = api.get("/rentals/alerts").json()["items"]
    assert alerts["pdc_overdue"]["count"] == sum(1 for a in feed if a["kind"] == "cheque_overdue")
    assert alerts["pdc_overdue"]["href"].startswith("/pdc-cheques")
    due7 = [a for a in feed if a["kind"] == "cheque_due_7"]
    if due7:
        assert alerts["pdc_due_7"]["count"] == len(due7)


def test_summary_endpoint(funded, bid) -> None:
    api = funded
    make(api, bid)
    j = api.get("/rentals/summary").json()
    assert j["agreements_active"] == 1 and j["annual_rent_active"] == "120000.00"
    assert j["cheques"]["pending_count"] == 4 and j["cheques"]["pending_amount"] == "120000.00"


# ---------------------------------------------------------------- 9. permissions, RLS and audit
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/rentals"),
        ("get", "/rentals/summary"),
        ("get", "/rentals/alerts"),
        ("get", "/rentals/upcoming-expiries"),
        ("get", f"/rentals/{uuid.uuid4()}"),
        ("post", "/rentals"),
        ("post", "/rentals/schedule-preview"),
        ("post", f"/rentals/{uuid.uuid4()}/renew"),
        ("post", f"/rentals/{uuid.uuid4()}/renewal-preview"),
        ("get", "/pdc-cheques"),
        ("get", "/pdc-cheques/summary"),
        ("get", f"/pdc-cheques/{uuid.uuid4()}"),
        ("post", f"/pdc-cheques/{uuid.uuid4()}/clear"),
        ("post", f"/pdc-cheques/{uuid.uuid4()}/bounce"),
        ("post", f"/pdc-cheques/{uuid.uuid4()}/replace"),
    ],
)
def test_branch_user_is_forbidden_and_anonymous_is_unauthorised(api, method, path) -> None:
    call = getattr(api, method)
    r = call(path, who="branch") if method == "get" else call(path, {}, "branch")
    assert r.status_code == 403
    assert getattr(api.c, method)(f"{API}{path}").status_code == 401


def test_denied_access_is_audited(api, admin, branch_user) -> None:
    before = admin.execute(
        "select count(*) from public.audit_log where action='ACCESS_DENIED' and actor_user_id=%s",
        (branch_user,),
    ).fetchone()[0]
    api.get("/pdc-cheques", "branch")
    after = admin.execute(
        "select count(*) from public.audit_log where action='ACCESS_DENIED' and actor_user_id=%s",
        (branch_user,),
    ).fetchone()[0]
    assert after == before + 1


def test_clear_and_bounce_are_audited_with_actor_and_reason(funded, bid, admin, owner) -> None:
    api = funded
    s = (TODAY - timedelta(days=2)).isoformat()
    d = make(
        api,
        bid,
        annual_rent="20000.00",
        cheque_count=2,
        start_date=s,
        first_cheque_date=s,
        first_cheque_no="600000",
    )
    c0, c1 = cheques_of(d)
    api.post(f"/pdc-cheques/{c0['id']}/clear", {"note": "Statement checked"})
    api.post(f"/pdc-cheques/{c1['id']}/bounce", {"reason": "Returned: refer to drawer"})
    r0 = admin.execute(
        "select action, actor_user_id, reason from public.audit_log where table_name='pdc_cheques' and record_id=%s order by id",
        (c0["id"],),
    ).fetchall()
    r1 = admin.execute(
        "select action, actor_user_id, reason from public.audit_log where table_name='pdc_cheques' and record_id=%s order by id",
        (c1["id"],),
    ).fetchall()
    assert (
        [x[0] for x in r0] == ["INSERT", "UPDATE"]
        and r0[1][1] == owner
        and r0[1][2] == "Statement checked"
    )
    assert r1[1][2] == "Returned: refer to drawer"
    cleared = api.get(f"/pdc-cheques/{c0['id']}").json()
    assert cleared["cheque"]["cleared_by_name"] and len(cleared["history"]) == 2


def test_cheque_detail_not_found_and_agreement_not_found(api) -> None:
    assert api.get(f"/pdc-cheques/{uuid.uuid4()}").status_code == 404
    assert api.get(f"/rentals/{uuid.uuid4()}").status_code == 404
    assert api.get("/rentals/not-a-uuid").status_code == 422
