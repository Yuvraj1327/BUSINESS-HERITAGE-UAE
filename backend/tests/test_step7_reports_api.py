"""Step 7 API tests: daily reports, owner dashboard, Branch & Date View, missing detection, branch isolation.
Real FastAPI app + real PostgreSQL (migrations 0001-0011, RLS) as the restricted `app_api` role.
The test database is shared across modules, so every test uses its own date window and cleans what it adds."""

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.security import TokenVerifier
from app.main import create_app
from app.utils.time import dubai_today
from tests.conftest import make_settings
from tests.jwt_helpers import FakeJwks, KeyPair, claims

pytestmark = pytest.mark.integration

API = "/api/v1"
START = date(
    2026, 3, 1
)  # reporting start used by the "configured" fixture (opening balance as of 2026-02-28)


@pytest.fixture(scope="module")
def key() -> KeyPair:
    return KeyPair("kid-step7")


@pytest.fixture(scope="module")
def admin(pg_admin_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_admin_dsn, autocommit=True) as c:
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
def main_user(admin, bid) -> uuid.UUID:
    return _user(admin, "branch", bid["ALSAFA MAIN"])


@pytest.fixture(scope="module")
def jernas_user(admin, bid) -> uuid.UUID:
    return _user(admin, "branch", bid["JERNAS"])


@pytest.fixture()
def client(app_api_url: str, key: KeyPair) -> Iterator[TestClient]:
    settings = make_settings(supabase_url="https://abcd.supabase.test", database_url=app_api_url)
    app = create_app(settings)
    app.state.token_verifier = TokenVerifier(settings, fetcher=FakeJwks(key))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def configured(admin) -> Iterator[None]:
    """Opening balance saved as of 2026-02-28 -> reporting starts 2026-03-01. Removed afterwards."""
    admin.execute("delete from public.opening_balances")
    admin.execute(
        "insert into public.opening_balances (id, as_of_date, receipts_bank, enbd_balance, adcb_balance, pos_pending)"
        " values (1, %s, 'ENBD', 1000, 500, 200)",
        (START - timedelta(days=1),),
    )
    yield
    admin.execute("delete from public.opening_balances")


@pytest.fixture()
def unconfigured(admin) -> Iterator[None]:
    admin.execute("delete from public.opening_balances")
    yield


def h(key: KeyPair, uid: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {key.sign(claims(uid))}"}


def err(r) -> str:
    return r.json()["error"]["code"]


def body(d: date, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "report_date": d.isoformat(),
        "total_sales": "1000.00",
        "order_count": 10,
        "cash_received": "600.00",
        "pos_amount": "200.00",
        "bank_transfer": "100.00",
        "link_payment": "50.00",
        "shop_expenses": "300.00",
        "shop_savings": "100.00",
    }
    base.update(over)
    return base


def insert(
    admin,
    branch: uuid.UUID,
    d: date,
    sales: int = 100,
    cash: int | None = None,
    exp: int = 0,
    sav: int = 0,
):
    return admin.execute(
        """insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received,
                                             shop_expenses, shop_savings)
           values (%s,%s,%s,1,%s,%s,%s) returning id""",
        (d, branch, sales, sales if cash is None else cash, exp, sav),
    ).fetchone()[0]


# ---- submit / validation --------------------------------------------------------------------------------
def test_owner_submits_and_response_has_server_side_reconciliation(client, key, owner, bid) -> None:
    d = date(2026, 4, 1)
    r = client.post(
        f"{API}/daily-reports", json=body(d, branch_id=str(bid["SATWA"])), headers=h(key, owner)
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["total_received"] == "950.00" and j["difference"] == "50.00" and j["check"] == "Diff"
    assert j["shop_expenses_excl_savings"] == "200.00" and j["branch_name"] == "SATWA"


def test_branch_user_branch_is_automatic(client, key, main_user, bid) -> None:
    r = client.post(f"{API}/daily-reports", json=body(date(2026, 4, 2)), headers=h(key, main_user))
    assert r.status_code == 201 and r.json()["branch_id"] == str(bid["ALSAFA MAIN"])


def test_branch_user_cannot_submit_for_another_branch(client, key, main_user, bid, admin) -> None:
    d = date(2026, 4, 3)
    r = client.post(
        f"{API}/daily-reports",
        json=body(d, branch_id=str(bid["JERNAS"])),
        headers=h(key, main_user),
    )
    assert r.status_code == 403 and err(r) == "branch_access_denied"
    assert (
        admin.execute(
            "select count(*) from public.daily_reports where report_date=%s", (d,)
        ).fetchone()[0]
        == 0
    )


def test_owner_must_choose_an_active_branch(client, key, owner) -> None:
    r = client.post(f"{API}/daily-reports", json=body(date(2026, 4, 4)), headers=h(key, owner))
    assert r.status_code == 422 and "branch_id" in r.json()["error"]["fields"]
    r = client.post(
        f"{API}/daily-reports",
        json=body(date(2026, 4, 4), branch_id=str(uuid.uuid4())),
        headers=h(key, owner),
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "over",
    [
        {"total_sales": "0"},
        {"total_sales": "-5"},
        {"cash_received": "-1"},
        {"pos_amount": "-0.01"},
        {"total_sales": "10.123"},
        {"shop_savings": "400.00", "shop_expenses": "300.00"},
        {"order_count": -1},
        {"unknown_field": 1},
    ],
)
def test_invalid_payloads_are_rejected(client, key, main_user, admin, over) -> None:
    d = date(2026, 4, 10)
    r = client.post(f"{API}/daily-reports", json=body(d, **over), headers=h(key, main_user))
    assert r.status_code == 422, r.text
    assert (
        admin.execute(
            "select count(*) from public.daily_reports where report_date=%s", (d,)
        ).fetchone()[0]
        == 0
    )


def test_future_dubai_date_is_rejected(client, key, main_user) -> None:
    tomorrow = dubai_today() + timedelta(days=1)
    r = client.post(f"{API}/daily-reports", json=body(tomorrow), headers=h(key, main_user))
    assert r.status_code == 422 and "report_date" in r.json()["error"]["fields"]


def test_date_defaults_to_dubai_today(client, key, jernas_user, admin, bid) -> None:
    payload = body(date(2026, 1, 1))
    del payload["report_date"]
    r = client.post(f"{API}/daily-reports", json=payload, headers=h(key, jernas_user))
    try:
        assert r.status_code in (201, 409)
        if r.status_code == 201:
            assert r.json()["report_date"] == dubai_today().isoformat()
    finally:
        pass


def test_duplicate_branch_date_is_409_and_db_enforces_it_too(
    client, key, main_user, bid, admin
) -> None:
    d = date(2026, 4, 11)
    assert (
        client.post(f"{API}/daily-reports", json=body(d), headers=h(key, main_user)).status_code
        == 201
    )
    r = client.post(f"{API}/daily-reports", json=body(d), headers=h(key, main_user))
    assert r.status_code == 409 and err(r) == "duplicate_report"
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert(admin, bid["ALSAFA MAIN"], d)


def test_voided_report_frees_the_date_and_only_owner_can_void(
    client, key, owner, main_user, bid, admin
) -> None:
    d = date(2026, 4, 12)
    rid = client.post(f"{API}/daily-reports", json=body(d), headers=h(key, main_user)).json()["id"]
    # branch user: no void
    assert (
        client.post(
            f"{API}/daily-reports/{rid}/void", json={"reason": "typo"}, headers=h(key, main_user)
        ).status_code
        == 403
    )
    # owner: reason required
    assert (
        client.post(
            f"{API}/daily-reports/{rid}/void", json={"reason": ""}, headers=h(key, owner)
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{API}/daily-reports/{rid}/void",
            json={"reason": "wrong amounts"},
            headers=h(key, owner),
        ).status_code
        == 204
    )
    assert client.get(f"{API}/daily-reports/{rid}", headers=h(key, owner)).status_code == 404
    assert (
        client.post(f"{API}/daily-reports", json=body(d), headers=h(key, main_user)).status_code
        == 201
    )


def test_no_edit_or_delete_routes_exist(client, key, owner, main_user) -> None:
    rid = client.post(
        f"{API}/daily-reports", json=body(date(2026, 4, 13)), headers=h(key, main_user)
    ).json()["id"]
    for method in ("PUT", "PATCH", "DELETE"):
        for who in (owner, main_user):
            assert (
                client.request(
                    method,
                    f"{API}/daily-reports/{rid}",
                    headers=h(key, who),
                    json=body(date(2026, 4, 13)),
                ).status_code
                == 405
            )


# ---- list / get isolation -----------------------------------------------------------------------------------
def test_list_pagination_and_branch_isolation(
    client, key, owner, main_user, jernas_user, bid, admin
) -> None:
    for i in range(30):
        insert(admin, bid["MIRDIF"], date(2026, 5, 1) + timedelta(days=i))
    insert(admin, bid["ALSAFA MAIN"], date(2026, 5, 5))
    p = {"date_from": "2026-05-01", "date_to": "2026-05-31"}
    r = client.get(f"{API}/daily-reports", params=p, headers=h(key, owner)).json()
    assert r["total"] == 31 and len(r["items"]) == 25 and r["page_size"] == 25
    dates = [i["report_date"] for i in r["items"]]
    assert dates == sorted(dates, reverse=True)
    r2 = client.get(f"{API}/daily-reports", params={**p, "page": 2}, headers=h(key, owner)).json()
    assert len(r2["items"]) == 6
    mine = client.get(f"{API}/daily-reports", params=p, headers=h(key, main_user)).json()
    assert {i["branch_name"] for i in mine["items"]} == {"ALSAFA MAIN"}
    assert (
        client.get(
            f"{API}/daily-reports",
            params={**p, "branch_id": str(bid["MIRDIF"])},
            headers=h(key, main_user),
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"{API}/daily-reports", params={"page_size": 101}, headers=h(key, owner)
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{API}/daily-reports",
            params={"date_from": "2026-05-10", "date_to": "2026-05-01"},
            headers=h(key, owner),
        ).status_code
        == 422
    )
    assert (
        client.get(f"{API}/daily-reports", params=p, headers=h(key, jernas_user)).json()["total"]
        == 0
    )


def test_get_one_other_branch_is_not_visible(client, key, owner, main_user, bid, admin) -> None:
    rid = insert(admin, bid["KARAMA"], date(2026, 5, 20))
    assert client.get(f"{API}/daily-reports/{rid}", headers=h(key, owner)).status_code == 200
    r = client.get(f"{API}/daily-reports/{rid}", headers=h(key, main_user))
    assert r.status_code in (403, 404) and "KARAMA" not in r.text


def test_unauthenticated_and_bad_tokens_rejected(client, key) -> None:
    for path in (
        "/daily-reports",
        "/dashboard/owner",
        "/branch-date-view?date_from=2026-05-01&date_to=2026-05-02",
    ):
        assert client.get(f"{API}{path}").status_code == 401
        assert (
            client.get(f"{API}{path}", headers={"Authorization": "Bearer nope"}).status_code == 401
        )
    assert client.post(f"{API}/daily-reports", json=body(date(2026, 4, 1))).status_code == 401


# ---- Branch & Date View --------------------------------------------------------------------------------------
def test_branch_date_view_totals_and_collections(client, key, owner, bid, admin) -> None:
    f, t = date(2026, 6, 1), date(2026, 6, 3)
    insert(admin, bid["BURDUBAI"], f, sales=100, cash=60, exp=20, sav=5)
    insert(admin, bid["BURDUBAI"], f + timedelta(days=1), sales=200, cash=200, exp=10, sav=0)
    q = {"branch_id": str(bid["BURDUBAI"]), "date_from": f.isoformat(), "date_to": t.isoformat()}
    j = client.get(f"{API}/branch-date-view", params=q, headers=h(key, owner)).json()
    assert j["totals"]["total_sales"] == "300.00" and j["totals"]["report_count"] == 2
    assert (
        j["totals"]["collections"]["total_received"] == "260.00"
        and j["totals"]["not_yet_received"] == "40.00"
    )
    assert (
        j["totals"]["shop_expenses_excl_savings"] == "25.00"
        and j["totals"]["shop_savings"] == "5.00"
    )
    assert len(j["reports"]) == 2 and j["head_office"] is not None


def test_branch_date_view_branch_user_is_scoped_and_has_no_head_office(
    client, key, main_user, bid, admin
) -> None:
    f = date(2026, 6, 10)
    insert(admin, bid["ALSAFA MAIN"], f, sales=50)
    insert(admin, bid["JERNAS"], f, sales=999)
    q = {"date_from": f.isoformat(), "date_to": f.isoformat()}
    j = client.get(f"{API}/branch-date-view", params=q, headers=h(key, main_user)).json()
    assert j["totals"]["total_sales"] == "50.00" and j["branch_id"] == str(bid["ALSAFA MAIN"])
    assert j["head_office"] is None and j["head_office_rows"] is None
    other = client.get(
        f"{API}/branch-date-view",
        params={**q, "branch_id": str(bid["JERNAS"])},
        headers=h(key, main_user),
    )
    assert other.status_code == 403 and "999" not in other.text


def test_branch_date_view_rejects_bad_ranges(client, key, owner) -> None:
    ok = {"date_from": "2026-06-01", "date_to": "2026-06-02"}
    assert (
        client.get(
            f"{API}/branch-date-view",
            params={"date_from": "2026-06-05", "date_to": "2026-06-01"},
            headers=h(key, owner),
        ).status_code
        == 422
    )
    far = (dubai_today() + timedelta(days=1)).isoformat()
    assert (
        client.get(
            f"{API}/branch-date-view", params={**ok, "date_to": far}, headers=h(key, owner)
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{API}/branch-date-view",
            params={"date_from": "2026-01-01", "date_to": "2026-06-01"},
            headers=h(key, owner),
        ).status_code
        == 422
    )


# ---- missing reports -------------------------------------------------------------------------------------------
def test_missing_not_configured_when_no_opening_balance(client, key, owner, unconfigured) -> None:
    q = {"date_from": "2026-07-01", "date_to": "2026-07-03"}
    j = client.get(f"{API}/daily-reports/missing", params=q, headers=h(key, owner)).json()
    assert (
        j["status"] == "not_configured" and j["missing_count"] == 0 and j["reporting_start"] is None
    )


def test_missing_before_start_and_start_clamp(client, key, owner, configured, bid, admin) -> None:
    j = client.get(
        f"{API}/daily-reports/missing",
        params={"date_from": "2026-02-01", "date_to": "2026-02-10"},
        headers=h(key, owner),
    ).json()
    assert j["status"] == "before_start" and j["missing_count"] == 0
    # range straddles the start: only days from 2026-03-01 count
    q = {"date_from": "2026-02-27", "date_to": "2026-03-02", "branch_id": str(bid["NDL"])}
    j = client.get(f"{API}/daily-reports/missing", params=q, headers=h(key, owner)).json()
    assert j["date_from"] == "2026-03-01" and j["expected"] == 2 and j["missing_count"] == 2


def test_missing_counts_branch_dates_and_matches_db_function(
    client, key, owner, configured, bid, admin
) -> None:
    f, t = date(2026, 8, 1), date(2026, 8, 3)
    insert(admin, bid["NDL"], f)
    q = {"date_from": f.isoformat(), "date_to": t.isoformat()}
    j = client.get(f"{API}/daily-reports/missing", params=q, headers=h(key, owner)).json()
    assert (
        j["status"] == "ok"
        and j["expected"] == 30
        and j["missing_count"] == 29
        and j["received"] == 1
    )
    ndl = next(b for b in j["branches"] if b["branch_name"] == "NDL")
    assert ndl["dates"] == ["2026-08-02", "2026-08-03"]
    satwa = next(b for b in j["branches"] if b["branch_name"] == "SATWA")
    assert satwa["missing_count"] == 3


def test_missing_branch_user_sees_only_own_branch(client, key, main_user, configured, bid) -> None:
    q = {"date_from": "2026-09-01", "date_to": "2026-09-02"}
    j = client.get(f"{API}/daily-reports/missing", params=q, headers=h(key, main_user)).json()
    assert [b["branch_name"] for b in j["branches"]] == ["ALSAFA MAIN"] and j["expected"] == 2
    assert (
        client.get(
            f"{API}/daily-reports/missing",
            params={**q, "branch_id": str(bid["SATWA"])},
            headers=h(key, main_user),
        ).status_code
        == 403
    )


def test_future_days_are_not_missing(client, key, owner, configured) -> None:
    today = dubai_today()
    q = {
        "date_from": (today + timedelta(days=1)).isoformat(),
        "date_to": (today + timedelta(days=3)).isoformat(),
    }
    j = client.get(f"{API}/daily-reports/missing", params=q, headers=h(key, owner)).json()
    assert j["missing_count"] == 0 and j["expected"] == 0


# ---- owner dashboard -------------------------------------------------------------------------------------------
def test_owner_dashboard_forbidden_for_branch_user(client, key, main_user) -> None:
    r = client.get(f"{API}/dashboard/owner", headers=h(key, main_user))
    assert r.status_code == 403 and err(r) == "permission_denied"


def test_owner_dashboard_day_aggregation_matches_rows(
    client, key, owner, bid, admin, unconfigured
) -> None:
    d = date(2026, 10, 5)
    insert(admin, bid["ALSAFA MAIN"], d, sales=1000, cash=900, exp=300, sav=100)
    insert(admin, bid["JERNAS"], d, sales=500, cash=500, exp=50, sav=0)
    cat = admin.execute(
        "insert into public.expense_categories (name) values (%s) returning id",
        (f"t-{uuid.uuid4().hex[:6]}",),
    ).fetchone()[0]
    for amt, saving, br in ((70, False, bid["JERNAS"]), (30, True, None)):
        admin.execute(
            "insert into public.head_office_expenses (expense_date, branch_id, category_id, amount, paid_from, is_saving)"
            " values (%s,%s,%s,%s,'Cash received',%s)",
            (d, br, cat, amt, saving),
        )
    j = client.get(
        f"{API}/dashboard/owner",
        params={"mode": "day", "date": d.isoformat()},
        headers=h(key, owner),
    ).json()
    k = j["kpis"]
    assert (
        k["total_sales"] == "1500.00"
        and k["total_received"] == "1400.00"
        and k["not_yet_received"] == "100.00"
    )
    assert k["shop_expenses_excl_savings"] == "250.00"  # (300-100) + (50-0)
    assert k["head_office_expenses_excl_savings"] == "70.00"  # 100 total - 30 saving
    assert k["total_savings"] == "130.00"  # 100 shop + 30 head office
    assert k["sales_minus_expenses"] == "1180.00"  # 1500 - 250 - 70
    assert k["total_orders"] == 2
    assert len(j["branches"]) == 10 and j["days"] is None
    assert sum(float(b["total_sales"]) for b in j["branches"]) == 1500.0
    assert j["balances"]["status"] == "not_configured" and k["cash_bank_balance"] is None
    assert j["missing"]["status"] == "not_configured"
    admin.execute("delete from public.head_office_expenses where category_id=%s", (cat,))


def test_owner_dashboard_month_has_day_rows_and_balances(
    client, key, owner, bid, admin, configured
) -> None:
    insert(admin, bid["SATWA"], date(2026, 11, 2), sales=400, cash=400)
    j = client.get(
        f"{API}/dashboard/owner",
        params={"mode": "month", "month": "2026-11"},
        headers=h(key, owner),
    ).json()
    assert j["date_from"] == "2026-11-01" and j["date_to"] == "2026-11-30"
    assert j["balances"]["status"] == "ok" and j["balances"]["total"] is not None
    assert j["days"] and sum(float(x["total_sales"]) for x in j["days"]) == float(
        j["kpis"]["total_sales"]
    )
    assert j["days"][-1]["date"] <= dubai_today().isoformat()


def test_owner_dashboard_balance_before_start(client, key, owner, configured) -> None:
    j = client.get(
        f"{API}/dashboard/owner",
        params={"mode": "day", "date": "2026-02-10"},
        headers=h(key, owner),
    ).json()
    assert j["balances"]["status"] == "before_start" and j["balances"]["total"] is None


def test_owner_dashboard_rejects_future_and_bad_month(client, key, owner) -> None:
    tomorrow = (dubai_today() + timedelta(days=1)).isoformat()
    assert (
        client.get(
            f"{API}/dashboard/owner", params={"date": tomorrow}, headers=h(key, owner)
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{API}/dashboard/owner",
            params={"mode": "month", "month": "2999-01"},
            headers=h(key, owner),
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{API}/dashboard/owner",
            params={"mode": "month", "month": "2026-13"},
            headers=h(key, owner),
        ).status_code
        == 422
    )


def test_ten_branches_unchanged(admin) -> None:
    assert admin.execute("select count(*) from public.branches").fetchone()[0] == 10


# ---- DB function for the reporting start (migration 0011) ----------------------------------------------------
def test_reporting_start_date_visible_to_branch_user_but_balances_not(
    app_api_url, main_user, configured
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.core.security import TokenClaims
    from app.database.session import Database

    db = Database(make_settings(database_url=app_api_url))
    gen = db.session_for(TokenClaims(main_user, None, None, None, 9999999999, None))
    s = next(gen)
    assert s.execute(text("select public.reporting_start_date()")).scalar() == START
    with pytest.raises(DBAPIError):
        s.execute(text("select * from public.app_balances(cast('2026-03-05' as date))")).all()
    s.rollback()
    gen.close()
    db.dispose()
