"""Step 9 API tests: employees, leave / six-month rule, visas & passports, trade licences, compliance alerts.
Own disposable database (fresh migrations 0001-0013), wiped before every test, so nothing depends on other modules.
Real FastAPI app + PostgreSQL + RLS as the restricted `app_api` role."""

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core import calculations as calc
from app.core.security import TokenVerifier
from app.main import create_app
from app.utils.time import dubai_today
from tests.conftest import _ROOT, APP_API_PASSWORD, make_settings
from tests.jwt_helpers import FakeJwks, KeyPair, claims

pytestmark = pytest.mark.integration
API = "/api/v1"
TODAY = dubai_today()


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def hr_dsn(pg_admin_dsn: str) -> Iterator[str]:
    name = f"alsafa_hr_{uuid.uuid4().hex[:8]}"
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
def app_url(hr_dsn: str) -> str:
    name = hr_dsn.rsplit("dbname=", 1)[1]
    return f"postgresql://app_api:{APP_API_PASSWORD}@/{name}?host=/tmp&port=54329"


@pytest.fixture(scope="module")
def key() -> KeyPair:
    return KeyPair("kid-step9")


@pytest.fixture(scope="module")
def admin(hr_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(hr_dsn, autocommit=True) as c:
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
    admin.execute("truncate public.license_renewals, public.trade_licenses, public.employees")
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


def emp(api, bid, **kw) -> dict:
    body = {
        "full_name": "Ravi Kumar",
        "branch_id": str(bid["ALSAFA MAIN"]),
        "role_title": "Presser",
        "monthly_salary": "1500.00",
        "passport_expiry": (TODAY + timedelta(days=400)).isoformat(),
        "visa_expiry": (TODAY + timedelta(days=400)).isoformat(),
    }
    body.update(kw)
    r = api.post("/employees", body)
    assert r.status_code == 201, r.text
    return r.json()["employee"]


def start_for(days_remaining: int) -> date:
    """A leave start whose six-calendar-month limit date is exactly TODAY + days_remaining."""
    target = TODAY + timedelta(days=days_remaining)
    for k in range(-40, 40):
        s = calc.add_calendar_months(target, -6) + timedelta(days=k)
        if calc.leave_limit_date(s) == target:
            return s
    raise AssertionError("no start found")


def put_on_leave(admin, emp_id: str, start: date) -> None:
    admin.execute(
        "update public.employees set status='Leave', leave_start=%s where id=%s", (start, emp_id)
    )


def lic(api, bid, **kw) -> dict:
    body = {
        "branch_id": str(bid["ALSAFA MAIN"]),
        "license_no": "TL-1001",
        "authority": "DED Dubai",
        "expiry_date": (TODAY + timedelta(days=200)).isoformat(),
        "renewal_fee": "2500.00",
    }
    body.update(kw)
    r = api.post("/trade-licenses", body)
    assert r.status_code == 201, r.text
    return r.json()["license"]


# ---------------------------------------------------------------- pure calendar / threshold logic
def test_calendar_months_month_end_and_leap_year() -> None:
    assert calc.add_calendar_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert calc.add_calendar_months(date(2023, 8, 31), 6) == date(2024, 2, 29)
    assert calc.add_calendar_months(date(2026, 1, 31), 6) == date(2026, 7, 31)
    assert calc.add_calendar_months(date(2026, 12, 15), 6) == date(2027, 6, 15)
    assert calc.leave_limit_date(date(2026, 3, 1)) == date(2026, 9, 1)
    assert calc.leave_limit_date(date(2026, 3, 1)) != date(2026, 3, 1) + timedelta(days=180)
    assert calc.add_one_year(date(2024, 2, 29)) == date(2025, 2, 28)
    assert calc.add_one_year(date(2026, 5, 10)) == date(2027, 5, 10)


def test_leave_states_and_boundary() -> None:
    s = date(2026, 1, 15)
    limit = date(2026, 7, 15)
    assert calc.leave_info(s, limit - timedelta(days=31)).state == "on_leave"
    assert calc.leave_info(s, limit - timedelta(days=30)).state == "approaching_limit"
    assert calc.leave_info(s, limit - timedelta(days=1)).state == "approaching_limit"
    assert calc.leave_info(s, limit).state == "limit_reached"
    assert calc.leave_info(s, limit).days_remaining == 0
    assert calc.leave_info(s, limit + timedelta(days=1)).state == "visa_cancelled"
    assert calc.leave_info(s, s, visa_cancelled=True).state == "visa_cancelled"
    assert not calc.returns_after_limit(s, limit)
    assert calc.returns_after_limit(s, limit + timedelta(days=1))


def test_expiry_thresholds() -> None:
    t = TODAY
    d = timedelta
    assert calc.visa_status(t - d(days=1), t)[0] == "expired"
    assert calc.visa_status(t + d(days=30), t)[0] == "urgent"
    assert calc.visa_status(t + d(days=31), t)[0] == "upcoming"
    assert calc.visa_status(t + d(days=90), t)[0] == "upcoming"
    assert calc.visa_status(t + d(days=91), t)[0] == "normal"
    assert calc.passport_status(t + d(days=30), t)[0] == "urgent"
    assert calc.passport_status(t + d(days=180), t)[0] == "upcoming"
    assert calc.passport_status(t + d(days=181), t)[0] == "normal"
    assert calc.visa_status(None, t)[0] == "not_recorded"
    assert calc.license_status(t - d(days=1), t)[0] == "expired"


def test_sql_and_python_agree_on_six_months(admin) -> None:
    for s in (
        date(2023, 8, 31),
        date(2024, 2, 29),
        date(2026, 1, 31),
        date(2025, 12, 30),
        date(2026, 5, 31),
    ):
        sql = admin.execute("select %s::date + interval '6 months'", (s,)).fetchone()[0].date()
        assert sql == calc.leave_limit_date(s)


# ---------------------------------------------------------------- employees
def test_create_validation_and_no_identity_numbers(api, bid) -> None:
    base = {"full_name": "A", "branch_id": str(bid["ALSAFA MAIN"]), "monthly_salary": "100"}
    assert api.post("/employees", base).status_code == 201
    assert api.post("/employees", {**base, "full_name": ""}).status_code == 422
    assert api.post("/employees", {**base, "monthly_salary": "-1"}).status_code == 422
    assert api.post("/employees", {**base, "monthly_salary": "abc"}).status_code == 422
    assert api.post("/employees", {**base, "branch_id": str(uuid.uuid4())}).status_code == 422
    assert api.post("/employees", {**base, "visa_expiry": "1990-01-01"}).status_code == 422
    for field in ("passport_number", "emirates_id", "status", "visa_cancelled"):
        assert api.post("/employees", {**base, field: "x"}).status_code == 422


def test_no_identity_columns_in_database(admin) -> None:
    cols = {
        r[0]
        for r in admin.execute(
            "select column_name from information_schema.columns where table_name='employees'"
        )
    }
    assert not {c for c in cols if "number" in c or "emirates" in c or c.endswith("_no")}


def test_update_requires_reason_for_sensitive_changes(api, bid) -> None:
    e = emp(api, bid)
    body = {
        "full_name": "Ravi K",
        "branch_id": e["branch_id"],
        "role_title": "Presser",
        "monthly_salary": "1500.00",
        "passport_expiry": e["passport_expiry"],
        "visa_expiry": e["visa_expiry"],
    }
    assert api.put(f"/employees/{e['id']}", body).status_code == 200  # name only: no reason needed
    r = api.put(f"/employees/{e['id']}", {**body, "monthly_salary": "1800.00"})
    assert r.status_code == 422 and code(r) == "reason_required"
    r = api.put(
        f"/employees/{e['id']}", {**body, "monthly_salary": "1800.00", "reason": "Annual raise"}
    )
    assert r.status_code == 200 and r.json()["employee"]["monthly_salary"] == "1800.00"
    hist = r.json()["history"]
    assert any(h.get("reason") == "Annual raise" for h in hist)
    r = api.put(
        f"/employees/{e['id']}", {**body, "branch_id": str(bid["AL BARSHA"]), "reason": "Transfer"}
    )
    assert r.json()["employee"]["branch_name"] == "AL BARSHA"


def test_status_change_rules(api, bid) -> None:
    e = emp(api, bid)
    p = f"/employees/{e['id']}/status"
    assert (
        api.post(p, {"status": "On Leave", "reason": "Home leave"}).status_code == 422
    )  # needs start
    assert (
        code(api.post(p, {"status": "On Leave", "reason": "Home leave"})) == "leave_start_required"
    )
    future = (TODAY + timedelta(days=1)).isoformat()
    assert (
        api.post(p, {"status": "On Leave", "leave_start": future, "reason": "x y"}).status_code
        == 422
    )
    assert (
        api.post(p, {"status": "On Leave", "leave_start": TODAY.isoformat()}).status_code == 422
    )  # reason
    ok = api.post(
        p, {"status": "On Leave", "leave_start": TODAY.isoformat(), "reason": "Home leave"}
    )
    assert ok.status_code == 200
    out = ok.json()["employee"]
    assert out["status"] == "On Leave" and out["leave"]["state"] == "on_leave"
    assert out["leave"]["limit_date"] == calc.leave_limit_date(TODAY).isoformat()
    assert (
        api.post(
            p, {"status": "On Leave", "leave_start": TODAY.isoformat(), "reason": "again"}
        ).status_code
        == 409
    )


def test_return_before_limit_keeps_visa(api, bid, admin) -> None:
    e = emp(api, bid)
    put_on_leave(admin, e["id"], start_for(10))
    got = api.get(f"/employees/{e['id']}").json()["employee"]
    assert got["leave"]["state"] == "approaching_limit" and got["leave"]["days_remaining"] == 10
    r = api.post(f"/employees/{e['id']}/return", {"reason": "Back at work"})
    out = r.json()["employee"]
    assert r.status_code == 200 and out["status"] == "Active" and not out["visa_cancelled"]
    assert out["leave"] is None and out["payroll_eligible"] is True


def test_return_on_limit_date_keeps_visa(api, bid, admin) -> None:
    e = emp(api, bid)
    put_on_leave(admin, e["id"], start_for(0))
    got = api.get(f"/employees/{e['id']}").json()["employee"]
    assert got["leave"]["state"] == "limit_reached" and got["status"] == "On Leave"
    out = api.post(f"/employees/{e['id']}/return", {"reason": "Back on last day"}).json()[
        "employee"
    ]
    assert out["status"] == "Active" and not out["visa_cancelled"]


def test_return_after_limit_is_permanent_cancellation(api, bid, admin) -> None:
    e = emp(api, bid)
    put_on_leave(admin, e["id"], start_for(-3))
    got = api.get(f"/employees/{e['id']}").json()["employee"]
    assert got["status"] == "Visa Cancelled" and got["leave"]["state"] == "visa_cancelled"
    assert got["payroll_eligible"] is False
    r = api.post(f"/employees/{e['id']}/return", {"reason": "Came back late"})
    out = r.json()["employee"]
    assert r.status_code == 200 and out["visa_cancelled"] and out["status"] == "Visa Cancelled"
    assert out["stored_status"] == "Active" and out["leave"] is None
    assert out["visa_cancelled_date"] == calc.leave_limit_date(start_for(-3)).isoformat()
    # permanent: no leave again, no new cancellation, visa date frozen
    assert (
        code(
            api.post(
                f"/employees/{e['id']}/status",
                {"status": "On Leave", "leave_start": TODAY.isoformat(), "reason": "try"},
            )
        )
        == "visa_cancelled"
    )
    assert (
        code(
            api.post(
                f"/employees/{e['id']}/status", {"status": "Visa Cancelled", "reason": "again"}
            )
        )
        == "visa_already_cancelled"
    )
    assert (
        api.post(
            f"/employees/{e['id']}/status", {"status": "Active", "reason": "undo?"}
        ).status_code
        == 409
    )
    r = api.patch(
        f"/visas-passports/employees/{e['id']}/visa-expiry",
        {"expiry_date": (TODAY + timedelta(days=500)).isoformat()},
    )
    assert r.status_code == 422


def test_manual_visa_cancellation(api, bid) -> None:
    e = emp(api, bid)
    r = api.post(f"/employees/{e['id']}/status", {"status": "Visa Cancelled", "reason": "Resigned"})
    out = r.json()["employee"]
    assert out["status"] == "Visa Cancelled" and out["visa_cancelled_date"] == TODAY.isoformat()
    assert api.get("/employees/summary").json()["visa_cancelled"] == 1


def test_return_date_validation(api, bid, admin) -> None:
    e = emp(api, bid)
    s = TODAY - timedelta(days=20)
    put_on_leave(admin, e["id"], s)
    p = f"/employees/{e['id']}/return"
    assert (
        api.post(
            p, {"return_date": (s - timedelta(days=1)).isoformat(), "reason": "bad"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            p, {"return_date": (TODAY + timedelta(days=1)).isoformat(), "reason": "bad"}
        ).status_code
        == 422
    )
    assert (
        code(
            api.post(f"/employees/{emp(api, bid, full_name='B')['id']}/return", {"reason": "nope"})
        )
        == "not_on_leave"
    )


def test_leave_correction_and_history(api, bid, admin) -> None:
    e = emp(api, bid)
    put_on_leave(admin, e["id"], TODAY - timedelta(days=10))
    p = f"/employees/{e['id']}/leave"
    assert (
        api.patch(p, {"leave_start": (TODAY - timedelta(days=30)).isoformat()}).status_code == 422
    )  # reason
    r = api.patch(
        p, {"leave_start": (TODAY - timedelta(days=30)).isoformat(), "reason": "Wrong date entered"}
    )
    assert r.status_code == 200 and r.json()["employee"]["leave"]["days_on_leave"] == 30
    assert (
        api.patch(
            p, {"leave_start": (TODAY + timedelta(days=2)).isoformat(), "reason": "future"}
        ).status_code
        == 422
    )
    assert any(h.get("reason") == "Wrong date entered" for h in r.json()["history"])


def test_summary_cards_and_payroll(api, bid, admin) -> None:
    a = emp(api, bid, full_name="Active One", monthly_salary="1000.00")
    emp(api, bid, full_name="Active Two", monthly_salary="2000.50")
    leaver = emp(api, bid, full_name="Leaver", monthly_salary="900.00")
    c = emp(api, bid, full_name="Cancelled", monthly_salary="800.00")
    n = emp(api, bid, full_name="Near Limit", monthly_salary="700.00")
    z = emp(api, bid, full_name="Archived", monthly_salary="600.00")
    put_on_leave(admin, leaver["id"], TODAY - timedelta(days=5))
    put_on_leave(admin, n["id"], start_for(12))
    api.post(f"/employees/{c['id']}/status", {"status": "Visa Cancelled", "reason": "Resigned"})
    assert api.post(f"/employees/{z['id']}/archive", {"reason": "Left company"}).status_code == 204
    s = api.get("/employees/summary").json()
    assert s["total_active"] == 2
    assert s["on_leave"] == 2
    assert s["close_to_limit"] == 1
    assert s["visa_cancelled"] == 1
    assert s["monthly_payroll"] == "3000.50"
    assert s["payroll_employees"] == 2
    ls = api.get("/employees/leave/summary").json()
    assert ls["on_leave"] == 2 and ls["approaching"] == 1
    assert [i["full_name"] for i in ls["items"]] == ["Near Limit"]
    assert a["id"]


def test_list_search_filter_sort_paginate(api, bid, admin) -> None:
    emp(api, bid, full_name="Zed", monthly_salary="300.00")
    emp(api, bid, full_name="Amir", monthly_salary="900.00", branch_id=str(bid["AL BARSHA"]))
    x = emp(api, bid, full_name="Maya", monthly_salary="600.00")
    put_on_leave(admin, x["id"], TODAY - timedelta(days=2))
    names = lambda r: [i["full_name"] for i in r.json()["items"]]  # noqa: E731
    assert names(api.get("/employees")) == ["Amir", "Maya", "Zed"]
    assert names(api.get("/employees", sort="salary", desc="true")) == ["Amir", "Maya", "Zed"]
    assert names(api.get("/employees", q="ma")) == ["Maya"]
    assert names(api.get("/employees", branch_id=str(bid["AL BARSHA"]))) == ["Amir"]
    assert names(api.get("/employees", status="On Leave")) == ["Maya"]
    assert names(api.get("/employees", status="Active")) == ["Amir", "Zed"]
    p2 = api.get("/employees", page_size=2, page=2)
    assert p2.json()["total"] == 3 and names(p2) == ["Zed"]
    assert api.get("/employees", status="Retired").status_code == 422


def test_archive_is_not_a_delete(api, bid, admin) -> None:
    e = emp(api, bid)
    assert api.post(f"/employees/{e['id']}/archive", {"reason": "x"}).status_code == 422
    assert api.post(f"/employees/{e['id']}/archive", {"reason": "Left company"}).status_code == 204
    assert api.get("/employees").json()["total"] == 0
    assert api.get("/employees", include_archived="true").json()["total"] == 1
    assert (
        code(
            api.post(f"/employees/{e['id']}/status", {"status": "Visa Cancelled", "reason": "x y"})
        )
        == "employee_archived"
    )
    assert admin.execute("select count(*) from public.employees").fetchone()[0] == 1
    assert api.c.delete(f"{API}/employees/{e['id']}", headers=api.h()).status_code in (404, 405)


def test_audit_trail_records_user_and_reason(api, bid, admin, owner) -> None:
    e = emp(api, bid)
    api.post(f"/employees/{e['id']}/status", {"status": "Visa Cancelled", "reason": "Resigned"})
    rows = admin.execute(
        "select action, actor_user_id, reason from public.audit_log where table_name='employees' and record_id=%s order by id",
        (e["id"],),
    ).fetchall()
    assert [r[0] for r in rows] == ["INSERT", "UPDATE"]
    assert all(r[1] == owner for r in rows) and rows[1][2] == "Resigned"
    got = api.get(f"/employees/{e['id']}").json()["employee"]
    assert got["created_by_name"] and got["updated_by_name"] and got["created_at"]


# ---------------------------------------------------------------- visas & passports
def test_visa_passport_buckets_and_lists(api, bid) -> None:
    d = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
    emp(api, bid, full_name="Expired", visa_expiry=d(-5), passport_expiry=d(-1))
    emp(api, bid, full_name="Urgent", visa_expiry=d(30), passport_expiry=d(30))
    emp(api, bid, full_name="Upcoming", visa_expiry=d(90), passport_expiry=d(180))
    emp(api, bid, full_name="Normal", visa_expiry=d(91), passport_expiry=d(181))
    emp(api, bid, full_name="Blank", visa_expiry=None, passport_expiry=None)
    s = api.get("/visas-passports/summary").json()
    assert (
        s["visas"]["expired"],
        s["visas"]["urgent"],
        s["visas"]["upcoming"],
        s["visas"]["normal"],
    ) == (1, 1, 1, 1)
    assert (
        s["passports"]["expired"],
        s["passports"]["urgent"],
        s["passports"]["upcoming"],
        s["passports"]["normal"],
    ) == (1, 1, 1, 1)
    assert (
        s["visas"]["not_recorded"] == 1
        and s["visas_expiring_30"] == 1
        and s["passports_expiring_30"] == 1
    )
    assert s["passports_under_6_months"] == 2
    v = api.get("/visas-passports/visas").json()["items"]
    assert [i["employee_name"] for i in v][:4] == ["Expired", "Urgent", "Upcoming", "Normal"]
    assert [i["status"] for i in v][:4] == ["expired", "urgent", "upcoming", "normal"]
    assert v[1]["days_remaining"] == 30
    assert [
        i["employee_name"]
        for i in api.get("/visas-passports/visas", bucket="urgent").json()["items"]
    ] == ["Urgent"]
    assert [
        i["employee_name"] for i in api.get("/visas-passports/passports", q="norm").json()["items"]
    ] == ["Normal"]
    assert (
        api.get("/visas-passports/passports", branch_id=str(bid["AL BARSHA"])).json()["total"] == 0
    )


def test_cancelled_visa_listed_first_and_not_alerted(api, bid) -> None:
    emp(api, bid, full_name="Soon", visa_expiry=(TODAY + timedelta(days=3)).isoformat())
    c = emp(api, bid, full_name="Gone", visa_expiry=(TODAY + timedelta(days=300)).isoformat())
    api.post(f"/employees/{c['id']}/status", {"status": "Visa Cancelled", "reason": "Resigned"})
    items = api.get("/visas-passports/visas").json()["items"]
    assert items[0]["employee_name"] == "Gone" and items[0]["status"] == "cancelled"
    assert items[0]["employment_status"] == "Visa Cancelled"


def test_expiry_update_history(api, bid) -> None:
    e = emp(api, bid)
    new = (TODAY + timedelta(days=700)).isoformat()
    p = f"/visas-passports/employees/{e['id']}/visa-expiry"
    assert api.patch(p, {"expiry_date": e["visa_expiry"]}).status_code == 422
    assert api.patch(p, {"expiry_date": "1980-01-01"}).status_code == 422
    r = api.patch(p, {"expiry_date": new, "reason": "Renewed"})
    assert r.status_code == 200 and r.json()["employee"]["visa_expiry"] == new
    api.patch(f"/visas-passports/employees/{e['id']}/passport-expiry", {"expiry_date": new})
    h = api.get(f"/visas-passports/employees/{e['id']}/history").json()
    assert h["visa"][0]["old_expiry"] == e["visa_expiry"] and h["visa"][0]["new_expiry"] == new
    assert h["visa"][0]["reason"] == "Renewed" and h["visa"][0]["actor_name"]
    assert h["passport"][0]["new_expiry"] == new
    assert api.get(f"/visas-passports/employees/{uuid.uuid4()}/history").status_code == 404


# ---------------------------------------------------------------- trade licences
def test_license_create_validation_and_duplicates(api, bid) -> None:
    lic(api, bid)
    r = api.post(
        "/trade-licenses",
        {
            "branch_id": str(bid["AL BARSHA"]),
            "license_no": " tl-1001 ",
            "expiry_date": TODAY.isoformat(),
            "renewal_fee": "10",
        },
    )
    assert r.status_code == 409 and code(r) == "duplicate_license"
    assert (
        api.post(
            "/trade-licenses",
            {
                "branch_id": str(bid["AL BARSHA"]),
                "license_no": "",
                "expiry_date": TODAY.isoformat(),
                "renewal_fee": "10",
            },
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/trade-licenses",
            {
                "branch_id": str(bid["AL BARSHA"]),
                "license_no": "N",
                "expiry_date": TODAY.isoformat(),
                "renewal_fee": "-5",
            },
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/trade-licenses",
            {
                "branch_id": str(uuid.uuid4()),
                "license_no": "Q",
                "expiry_date": TODAY.isoformat(),
                "renewal_fee": "5",
            },
        ).status_code
        == 422
    )


def test_license_status_summary_and_fees_due(api, bid) -> None:
    d = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
    lic(api, bid, license_no="A-expired", expiry_date=d(-10), renewal_fee="100.00")
    lic(api, bid, license_no="B-20", expiry_date=d(20), renewal_fee="200.00")
    lic(api, bid, license_no="C-60", expiry_date=d(60), renewal_fee="300.00")
    lic(api, bid, license_no="D-90", expiry_date=d(90), renewal_fee="400.00")
    lic(api, bid, license_no="E-91", expiry_date=d(91), renewal_fee="500.00")
    s = api.get("/trade-licenses/summary").json()
    assert s["total"] == 5 and s["expired"] == 1 and s["expiring_30"] == 1 and s["expiring_60"] == 2
    assert s["renewal_fees_due"] == "1000.00" and s["fees_due_count"] == 4
    items = api.get("/trade-licenses").json()["items"]
    assert [i["license_no"] for i in items] == ["A-expired", "B-20", "C-60", "D-90", "E-91"]
    assert [i["status"] for i in items] == ["expired", "urgent", "upcoming", "upcoming", "normal"]
    assert [
        i["license_no"] for i in api.get("/trade-licenses", status="expired").json()["items"]
    ] == ["A-expired"]
    assert [i["license_no"] for i in api.get("/trade-licenses", q="c-6").json()["items"]] == [
        "C-60"
    ]
    assert api.get("/trade-licenses", q="dubai").json()["total"] == 5
    assert [
        i["license_no"] for i in api.get("/trade-licenses", sort="fee", desc="true").json()["items"]
    ][0] == "E-91"


def test_license_update_rules(api, bid) -> None:
    lic_ = lic(api, bid)
    body = {
        k: lic_[k]
        for k in ("branch_id", "license_no", "authority", "expiry_date", "renewal_fee", "notes")
    }
    assert (
        api.put(f"/trade-licenses/{lic_['id']}", {**body, "notes": "Renewed by agent"}).status_code
        == 200
    )
    r = api.put(f"/trade-licenses/{lic_['id']}", {**body, "renewal_fee": "2600.00"})
    assert r.status_code == 422 and code(r) == "reason_required"
    r = api.put(
        f"/trade-licenses/{lic_['id']}",
        {**body, "renewal_fee": "2600.00", "reason": "Fee increased"},
    )
    assert r.status_code == 200 and r.json()["license"]["renewal_fee"] == "2600.00"


def test_license_renewal_adds_one_year_and_keeps_history(api, bid, admin, owner) -> None:
    e0 = TODAY + timedelta(days=15)
    lic_ = lic(api, bid, expiry_date=e0.isoformat())
    r = api.post(
        f"/trade-licenses/{lic_['id']}/renew",
        {"expected_expiry": e0.isoformat(), "note": "Paid at DED"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    new = calc.add_one_year(e0)
    assert out["license"]["expiry_date"] == new.isoformat() and out["license"]["renewal_count"] == 1
    assert out["license"]["last_renewed_on"] == TODAY.isoformat()
    ren = out["renewals"][0]
    assert ren["previous_expiry"] == e0.isoformat() and ren["new_expiry"] == new.isoformat()
    assert (
        ren["renewal_fee"] == "2500.00"
        and ren["renewed_on"] == TODAY.isoformat()
        and ren["created_by_name"]
    )
    # second renewal with an overridden fee; first renewal row is preserved
    r2 = api.post(
        f"/trade-licenses/{lic_['id']}/renew",
        {"expected_expiry": new.isoformat(), "renewal_fee": "2750.00"},
    )
    assert r2.status_code == 200
    rows = api.get(f"/trade-licenses/{lic_['id']}/renewals").json()
    assert len(rows) == 2 and {x["renewal_fee"] for x in rows} == {"2500.00", "2750.00"}
    assert {x["previous_expiry"] for x in rows} == {e0.isoformat(), new.isoformat()}
    assert any(h["action"] == "UPDATE" for h in r2.json()["history"])
    # the renewal history is immutable
    import psycopg

    with pytest.raises(psycopg.errors.Error):
        admin.execute("update public.license_renewals set renewal_fee = 1")
    with pytest.raises(psycopg.errors.Error):
        admin.execute("delete from public.license_renewals")


def test_license_double_click_and_stale_renewal_refused(api, bid) -> None:
    e0 = TODAY + timedelta(days=10)
    lic_ = lic(api, bid, expiry_date=e0.isoformat())
    key = str(uuid.uuid4())
    body = {"expected_expiry": e0.isoformat(), "client_key": key}
    assert api.post(f"/trade-licenses/{lic_['id']}/renew", body).status_code == 200
    again = api.post(f"/trade-licenses/{lic_['id']}/renew", body)  # same click repeated
    assert again.status_code == 409 and code(again) == "stale_renewal"
    keyed = api.post(
        f"/trade-licenses/{lic_['id']}/renew",
        {"expected_expiry": calc.add_one_year(e0).isoformat(), "client_key": key},
    )
    assert keyed.status_code == 409 and code(keyed) == "duplicate_transaction"
    assert len(api.get(f"/trade-licenses/{lic_['id']}/renewals").json()) == 1
    assert (
        api.get(f"/trade-licenses/{lic_['id']}").json()["license"]["expiry_date"]
        == calc.add_one_year(e0).isoformat()
    )


def test_license_renewal_leap_day_and_expired(api, bid) -> None:
    lic_ = lic(api, bid, license_no="LEAP", expiry_date="2028-02-29")
    out = api.post(f"/trade-licenses/{lic_['id']}/renew", {"expected_expiry": "2028-02-29"}).json()
    assert out["license"]["expiry_date"] == "2029-02-28"
    old = lic(api, bid, license_no="OLD", expiry_date=(TODAY - timedelta(days=400)).isoformat())
    out = api.post(
        f"/trade-licenses/{old['id']}/renew", {"expected_expiry": old["expiry_date"]}
    ).json()
    assert (
        out["license"]["expiry_date"] == calc.add_one_year(TODAY - timedelta(days=400)).isoformat()
    )
    assert out["license"]["status"] == "expired"  # +1 year from the old expiry, not from today


def test_license_archive(api, bid) -> None:
    lic_ = lic(api, bid)
    assert (
        api.post(f"/trade-licenses/{lic_['id']}/archive", {"reason": "Closed branch"}).status_code
        == 204
    )
    assert api.get("/trade-licenses").json()["total"] == 0
    assert (
        code(
            api.post(
                f"/trade-licenses/{lic_['id']}/renew", {"expected_expiry": lic_["expiry_date"]}
            )
        )
        == "license_archived"
    )
    lic(api, bid)  # the number can be reused once archived


# ---------------------------------------------------------------- alerts
def test_alert_feed_no_duplicates_and_links(api, bid, admin) -> None:
    d = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
    both = emp(api, bid, full_name="Both", visa_expiry=d(5), passport_expiry=d(-2))
    near = emp(api, bid, full_name="Near", visa_expiry=d(400), passport_expiry=d(400))
    gone = emp(api, bid, full_name="Gone", visa_expiry=d(-3), passport_expiry=d(400))
    put_on_leave(admin, near["id"], start_for(7))
    put_on_leave(admin, gone["id"], start_for(-1))
    l1 = lic(api, bid, license_no="L1", expiry_date=d(-1))
    l2 = lic(api, bid, license_no="L2", expiry_date=d(12))
    l3 = lic(api, bid, license_no="L3", expiry_date=d(75))
    lic(api, bid, license_no="L4", expiry_date=d(300))
    feed = api.get("/compliance/alerts").json()
    keys = [i["key"] for i in feed["items"]]
    assert len(keys) == len(set(keys)) == feed["total"]
    by = {(i["kind"], i["href"].rsplit("/", 1)[1]) for i in feed["items"]}
    assert ("visa_expiring", both["id"]) in by and ("passport_expired", both["id"]) in by
    assert ("leave_limit_approaching", near["id"]) in by
    assert ("visa_cancelled_by_leave", gone["id"]) in by
    assert (
        "visa_expired",
        gone["id"],
    ) not in by  # a cancelled visa is not also reported as expired
    assert ("license_expired", l1["id"]) in by and ("license_expiring", l2["id"]) in by
    assert ("license_renewal_due", l3["id"]) in by
    assert len(by) == len(feed["items"]) == 7
    assert all(i["href"].startswith(("/employees/", "/trade-licenses/")) for i in feed["items"])
    assert feed["danger"] + feed["warning"] == feed["total"]
    # renewing a licence clears its alert; the record is never reported twice
    api.post(f"/trade-licenses/{l2['id']}/renew", {"expected_expiry": l2["expiry_date"]})
    after = api.get("/compliance/alerts").json()
    assert after["total"] == 6 and not any(i["href"].endswith(l2["id"]) for i in after["items"])


def test_alerts_exclude_archived_records(api, bid) -> None:
    e = emp(api, bid, visa_expiry=(TODAY + timedelta(days=2)).isoformat())
    assert api.get("/compliance/alerts").json()["total"] == 1
    api.post(f"/employees/{e['id']}/archive", {"reason": "Left company"})
    assert api.get("/compliance/alerts").json()["total"] == 0


# ---------------------------------------------------------------- permissions
ENDPOINTS = [
    ("get", "/employees"),
    ("get", "/employees/summary"),
    ("get", "/employees/leave/summary"),
    ("get", f"/employees/{uuid.uuid4()}"),
    ("get", "/visas-passports/summary"),
    ("get", "/visas-passports/visas"),
    ("get", "/visas-passports/passports"),
    ("get", f"/visas-passports/employees/{uuid.uuid4()}/history"),
    ("get", "/trade-licenses"),
    ("get", "/trade-licenses/summary"),
    ("get", f"/trade-licenses/{uuid.uuid4()}"),
    ("get", f"/trade-licenses/{uuid.uuid4()}/renewals"),
    ("get", "/compliance/alerts"),
]
WRITES = [
    ("post", "/employees", {}),
    ("put", f"/employees/{uuid.uuid4()}", {}),
    ("post", f"/employees/{uuid.uuid4()}/status", {}),
    ("post", f"/employees/{uuid.uuid4()}/return", {}),
    ("patch", f"/employees/{uuid.uuid4()}/leave", {}),
    ("post", f"/employees/{uuid.uuid4()}/archive", {}),
    ("patch", f"/visas-passports/employees/{uuid.uuid4()}/visa-expiry", {}),
    ("patch", f"/visas-passports/employees/{uuid.uuid4()}/passport-expiry", {}),
    ("post", "/trade-licenses", {}),
    ("put", f"/trade-licenses/{uuid.uuid4()}", {}),
    ("post", f"/trade-licenses/{uuid.uuid4()}/renew", {}),
    ("post", f"/trade-licenses/{uuid.uuid4()}/archive", {}),
]


def test_branch_user_is_denied_everywhere(api, bid, admin, branch_user) -> None:
    e = emp(api, bid)
    for method, path in ENDPOINTS:
        r = getattr(api, method)(path, who="branch")
        assert r.status_code == 403, (method, path, r.status_code)
    for method, path, body in WRITES:
        r = getattr(api, method)(path, body, who="branch")
        assert r.status_code == 403, (method, path, r.status_code)
    assert api.get(f"/employees/{e['id']}", who="branch").status_code == 403
    denied = admin.execute(
        "select count(*) from public.audit_log where action='ACCESS_DENIED' and actor_user_id=%s",
        (branch_user,),
    ).fetchone()[0]
    assert denied >= len(ENDPOINTS)


def test_anonymous_is_rejected(client) -> None:
    for method, path in ENDPOINTS:
        assert getattr(client, method)(f"{API}{path}").status_code == 401


def test_rls_hides_hr_tables_from_non_owner(app_url, branch_user, owner, admin, bid) -> None:
    admin.execute(
        "insert into public.employees (full_name, branch_id, monthly_salary) values ('X', %s, 100)",
        (bid["ALSAFA MAIN"],),
    )
    with psycopg.connect(app_url) as c:
        for uid, expected in ((branch_user, 0), (owner, 1)):
            c.execute("begin")
            c.execute("set local role authenticated")
            c.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (f'{{"sub":"{uid}","role":"authenticated"}}',),
            )
            for t in ("employees", "trade_licenses", "license_renewals"):
                n = c.execute(f"select count(*) from public.{t}").fetchone()[0]
                assert (n == expected) if t == "employees" else n == 0
            c.execute("rollback")


def test_openapi_documents_hr_endpoints(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for p in (
        "/employees",
        "/employees/{employee_id}/return",
        "/visas-passports/summary",
        "/trade-licenses/{license_id}/renew",
        "/compliance/alerts",
    ):
        assert f"{API}{p}" in paths or p in paths


def test_step7_dashboard_alerts_use_hr_records(api, bid) -> None:
    d = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
    emp(api, bid, visa_expiry=d(4))
    lic(api, bid, license_no="D1", expiry_date=d(10))
    lic(api, bid, license_no="D2", expiry_date=d(60))
    alerts = {a["key"]: a for a in api.get("/dashboard/owner").json()["alerts"]}
    assert alerts["visas_30"]["count"] == 1 and alerts["visas_30"]["href"] == "/visas-passports"
    assert alerts["licenses_30"]["count"] == 1 and alerts["licenses_renewal_90"]["count"] == 1
    assert api.get("/dashboard/owner", who="branch").status_code in (200, 403)
