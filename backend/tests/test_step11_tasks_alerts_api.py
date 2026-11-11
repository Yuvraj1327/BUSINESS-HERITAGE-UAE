"""Step 11 API tests: tasks (rules, permissions, overdue, history) and the centralized alerts (generation, duplicate
prevention, read/acknowledge, resolution, dashboard consistency, Owner-only). Own disposable database (migrations 0001-0015).
Real FastAPI app + PostgreSQL + RLS as the restricted `app_api` role."""

import uuid
from collections.abc import Iterator
from datetime import timedelta

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
    name = f"alsafa_t11_{uuid.uuid4().hex[:8]}"
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
    return KeyPair("kid-step11")


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
        "truncate public.alerts, public.tasks, public.pdc_cheques, public.rental_agreements cascade"
    )
    admin.execute("delete from public.employees")
    admin.execute("delete from public.trade_licenses")
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


def d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def task(api, bid, title="Renew water contract", **over) -> dict:
    body = {"title": title, "branch_id": str(bid["ALSAFA MAIN"]), "due_date": d(3)}
    body.update(over)
    r = api.post("/tasks", body)
    assert r.status_code == 201, r.text
    return r.json()["task"]


def alerts(api, **p) -> list[dict]:
    r = api.get("/alerts", page_size=100, **p)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def kinds(api, **p) -> list[str]:
    return sorted(a["kind"] for a in alerts(api, **p))


def of(api, kind: str) -> list[dict]:
    return [a for a in alerts(api) if a["kind"] == kind]


def opening_body(bid) -> dict:
    return {
        "as_of_date": (TODAY - timedelta(days=9)).isoformat(),
        "receipts_bank": "ENBD",
        "enbd_balance": "10000.00",
        "adcb_balance": "5000.00",
        "pos_pending": "0.00",
        "savings_brought_forward": "0.00",
        "branch_cash": [{"branch_id": str(i), "amount": "0"} for i in bid.values()],
    }


@pytest.fixture()
def funded(api, bid) -> Api:
    assert api.put("/opening-balances", opening_body(bid)).status_code == 200
    return api


# ---------------------------------------------------------------- 1. tasks
def test_create_defaults_unassigned_to_do_and_traceable(api, bid, owner) -> None:
    t = task(api, bid)
    assert (
        t["status"] == "To Do" and t["assignee_id"] is None and t["assignee_name"] == "Unassigned"
    )
    assert t["completed_at"] is None and t["created_by_name"] and t["branch_name"] == "ALSAFA MAIN"
    assert t["timing"] == "upcoming" and t["days_to_due"] == 3
    h = api.get(f"/tasks/{t['id']}").json()["history"]
    assert len(h) == 1 and h[0]["action"] == "INSERT"


def test_all_branches_task_and_validation(api, bid) -> None:
    t = task(api, bid, "Group audit", branch_id=None)
    assert t["branch_name"] == "All Branches"
    assert api.post("/tasks", {"title": ""}).status_code == 422
    assert (
        api.post("/tasks", {"title": "x", "status": "Done"}).status_code == 422
    )  # extra field forbidden
    assert api.post("/tasks", {"title": "x", "branch_id": str(uuid.uuid4())}).status_code == 422
    assert api.post("/tasks", {"title": "x", "assignee_id": str(uuid.uuid4())}).status_code == 422


def test_status_transitions_and_completion_date(api, bid) -> None:
    t = task(api, bid)
    r = api.post(f"/tasks/{t['id']}/status", {"status": "In Progress"})
    assert r.status_code == 200 and r.json()["task"]["status"] == "In Progress"
    done = api.post(f"/tasks/{t['id']}/status", {"status": "Done"}).json()["task"]
    assert done["status"] == "Done" and done["completed_at"] and done["completed_by_name"]
    assert done["timing"] == "completed"
    again = api.post(f"/tasks/{t['id']}/status", {"status": "Done"})
    assert again.status_code == 409 and code(again) == "status_unchanged"
    reopened = api.post(f"/tasks/{t['id']}/status", {"status": "To Do"}).json()["task"]
    assert reopened["completed_at"] is None
    acts = [h["action"] for h in api.get(f"/tasks/{t['id']}").json()["history"]]
    assert acts.count("UPDATE") == 3


def test_assign_and_reassign_only_to_active_users(api, bid, owner, branch_user, admin) -> None:
    t = task(api, bid)
    r = api.put(
        f"/tasks/{t['id']}",
        {
            "title": t["title"],
            "branch_id": t["branch_id"],
            "due_date": t["due_date"],
            "assignee_id": str(branch_user),
        },
    )
    assert r.status_code == 200 and r.json()["task"]["assignee_id"] == str(branch_user)
    admin.execute("update public.profiles set is_active = false where user_id = %s", (branch_user,))
    try:
        bad = api.put(f"/tasks/{t['id']}", {"title": "t", "assignee_id": str(branch_user)})
        assert bad.status_code == 422
    finally:
        admin.execute(
            "update public.profiles set is_active = true where user_id = %s", (branch_user,)
        )
    assert str(owner) in [a["id"] for a in api.get("/tasks/assignees").json()]


def test_overdue_rules_dubai_date_and_done_excluded(api, bid) -> None:
    past = task(api, bid, "Past", due_date=d(-2))
    today = task(api, bid, "Today", due_date=d(0))
    soon = task(api, bid, "Soon", due_date=d(5))
    nodue = task(api, bid, "Someday", due_date=None)
    finished = task(api, bid, "Old but done", due_date=d(-9))
    api.post(f"/tasks/{finished['id']}/status", {"status": "Done"})
    timing = {t["title"]: t["timing"] for t in api.get("/tasks", page_size=100).json()["items"]}
    assert timing == {
        "Past": "overdue",
        "Today": "due_today",
        "Soon": "upcoming",
        "Someday": "no_due_date",
        "Old but done": "completed",
    }
    assert [t["id"] for t in api.get("/tasks/overdue").json()["items"]] == [past["id"]]
    up = [t["title"] for t in api.get("/tasks/upcoming").json()["items"]]
    assert up == ["Today", "Soon"]
    s = api.get("/tasks/summary").json()
    assert (
        s["total"],
        s["to_do"],
        s["in_progress"],
        s["done"],
        s["overdue"],
        s["due_today"],
        s["due_7"],
    ) == (5, 4, 0, 1, 1, 1, 2)
    assert today and soon and nodue


def test_search_filter_sort_paginate(api, bid) -> None:
    for i in range(5):
        task(
            api,
            bid,
            f"Cleaning job {i}",
            due_date=d(i + 1),
            description="deep clean" if i == 0 else None,
        )
    task(api, bid, "Visa copy", branch_id=str(bid["ALSAFA MAIN"]), due_date=d(20))
    assert len(api.get("/tasks", q="cleaning").json()["items"]) == 5
    assert len(api.get("/tasks", q="deep").json()["items"]) == 1  # description search
    p = api.get("/tasks", page_size=2, page=2).json()
    assert p["total"] == 6 and len(p["items"]) == 2
    desc = [t["title"] for t in api.get("/tasks", sort="due", desc="true").json()["items"]]
    assert desc[0] == "Visa copy"
    assert len(api.get("/tasks", unassigned="true").json()["items"]) == 6
    assert api.get("/tasks", due_from=d(3), due_to=d(5)).json()["total"] == 3
    assert api.get("/tasks", status="Done").json()["total"] == 0
    assert api.get("/tasks", sort="created").status_code == 200
    assert api.get("/tasks", all_branches="true").json()["total"] == 0


def test_branch_user_and_anonymous_have_no_task_access(api, bid, client) -> None:
    t = task(api, bid)
    for r in (
        api.get("/tasks", who="branch"),
        api.get(f"/tasks/{t['id']}", who="branch"),
        api.post("/tasks", {"title": "x"}, who="branch"),
        api.post(f"/tasks/{t['id']}/status", {"status": "Done"}, who="branch"),
        api.put(f"/tasks/{t['id']}", {"title": "hacked", "assignee_id": None}, who="branch"),
        api.get("/tasks/summary", who="branch"),
    ):
        assert r.status_code == 403
    assert client.get(f"{API}/tasks").status_code == 401
    assert api.get(f"/tasks/{t['id']}").json()["task"]["title"] == t["title"]


def test_task_audit_rows(api, bid, admin) -> None:
    t = task(api, bid)
    api.put(
        f"/tasks/{t['id']}", {"title": "Renamed", "branch_id": t["branch_id"], "reason": "typo"}
    )
    n = admin.execute(
        "select count(*) from public.audit_log where table_name='tasks' and record_id=%s",
        (str(t["id"]),),
    ).fetchone()[0]
    assert n == 2


# ---------------------------------------------------------------- 2. alerts
def test_overdue_task_alert_lifecycle(api, bid) -> None:
    t = task(api, bid, "Late one", due_date=d(-3))
    a = of(api, "task_overdue")
    assert len(a) == 1 and a[0]["severity"] == "warning" and a[0]["module"] == "tasks"
    assert a[0]["href"] == f"/tasks/{t['id']}" and a[0]["branch_name"] == "ALSAFA MAIN"
    assert a[0]["record_id"] == t["id"] and a[0]["due_date"] == d(-3) and a[0]["status"] == "unread"
    api.post(f"/tasks/{t['id']}/status", {"status": "Done"})
    assert of(api, "task_overdue") == []
    hist = api.get("/alerts/history").json()
    assert hist["total"] == 1 and hist["items"][0]["status"] == "resolved"


def test_task_due_today_and_week_alerts(api, bid) -> None:
    task(api, bid, "Today", due_date=d(0))
    task(api, bid, "Week", due_date=d(6))
    task(api, bid, "Later", due_date=d(8))
    got = {a["kind"]: a["severity"] for a in alerts(api)}
    assert got == {"task_due_today": "warning", "task_due_7": "info"}


def test_no_duplicates_across_repeated_reads(api, bid, admin) -> None:
    task(api, bid, due_date=d(-1))
    for _ in range(4):
        api.get("/alerts/summary")
        api.post("/alerts/refresh")
        alerts(api)
    assert admin.execute("select count(*) from public.alerts").fetchone()[0] == 1
    assert (
        admin.execute("select count(*) from public.alerts where resolved_at is null").fetchone()[0]
        == 1
    )


def test_changed_condition_updates_in_place(api, bid, admin) -> None:
    t = task(api, bid, due_date=d(-1))
    first = of(api, "task_overdue")[0]
    api.put(
        f"/tasks/{t['id']}",
        {"title": "Renamed task", "branch_id": t["branch_id"], "due_date": d(-4)},
    )
    second = of(api, "task_overdue")[0]
    assert (
        second["id"] == first["id"]
        and "Renamed task" in second["detail"]
        and second["due_date"] == d(-4)
    )
    assert admin.execute("select count(*) from public.alerts").fetchone()[0] == 1


def test_read_and_acknowledge_state(api, bid) -> None:
    task(api, bid, due_date=d(-1))
    a = alerts(api)[0]
    assert api.get("/alerts/unread-count").json() == {"unread": 1, "total_active": 1}
    r = api.post(f"/alerts/{a['id']}/read")
    assert r.status_code == 200 and r.json()["status"] == "read" and r.json()["read_at"]
    assert api.get("/alerts/unread-count").json() == {"unread": 0, "total_active": 1}
    ack = api.post(f"/alerts/{a['id']}/acknowledge").json()
    assert ack["status"] == "acknowledged" and ack["acknowledged_at"]
    assert alerts(api) == []  # leaves the active list
    h = api.get("/alerts/history", status="acknowledged").json()
    assert h["total"] == 1
    # acknowledged is not re-created by the next sync, and it is not duplicated
    api.post("/alerts/refresh")
    assert alerts(api) == [] and api.get("/alerts/history").json()["total"] == 1


def test_read_all_and_resolved_alert_cannot_be_acknowledged(api, bid) -> None:
    t = task(api, bid, due_date=d(-1))
    task(api, bid, "Two", due_date=d(0))
    a = [x for x in alerts(api) if x["kind"] == "task_overdue"][0]
    assert api.post("/alerts/read-all").json()["unread"] == 0
    api.post(f"/tasks/{t['id']}/status", {"status": "Done"})
    r = api.post(f"/alerts/{a['id']}/acknowledge")
    assert r.status_code == 409 and code(r) == "alert_resolved"
    assert api.post(f"/alerts/{uuid.uuid4()}/read").status_code == 404


def test_visa_and_passport_alerts_and_resolution(api, bid, admin) -> None:
    from tests.test_step9_hr_api import emp  # noqa: PLC0415  (same helper shape as Step 9)

    e = emp(api, bid, visa_expiry=d(10), passport_expiry=d(-3))
    ks = kinds(api)
    assert "visa_expiring" in ks and "passport_expired" in ks
    sev = {a["kind"]: a["severity"] for a in alerts(api)}
    assert sev["passport_expired"] == "critical" and sev["visa_expiring"] == "critical"
    admin.execute(
        "update public.employees set visa_expiry=%s, passport_expiry=%s where id=%s",
        (TODAY + timedelta(days=500), TODAY + timedelta(days=500), e["id"]),
    )
    assert kinds(api) == []
    assert api.get("/alerts/history", status="resolved").json()["total"] == 2


def test_trade_license_alert(api, bid) -> None:
    from tests.test_step9_hr_api import lic  # noqa: PLC0415

    lic(api, bid, expiry_date=d(12))
    a = of(api, "license_expiring")
    assert len(a) == 1 and a[0]["module"] == "trade_licenses" and a[0]["severity"] == "critical"


def test_missing_daily_report_alert_per_branch(api, bid) -> None:
    got = of(api, "report_missing")
    # reporting start is configured per database; whenever a branch has missing days it is ONE alert per branch
    assert len({a["record_id"] for a in got}) == len(got)
    assert all(a["href"] == "/branch-date-view" and a["severity"] == "warning" for a in got)


def test_rental_and_pdc_alerts(funded, bid) -> None:
    api = funded
    start = (TODAY - timedelta(days=2)).isoformat()
    dd = api.post(
        "/rentals",
        {
            "branch_id": str(bid["ALSAFA MAIN"]),
            "landlord": "Gulf Properties LLC",
            "unit": "Shop 1",
            "start_date": (TODAY - timedelta(days=350)).isoformat(),
            "annual_rent": "20000.00",
            "bank": "ENBD",
            "cheque_count": 2,
            "first_cheque_date": start,
            "first_cheque_no": "090000",
        },
    )
    assert dd.status_code == 201, dd.text
    ks = kinds(api)
    assert "rental_ending" in ks and "cheque_overdue" in ks
    first = dd.json()["schedule"]["items"][0]
    assert api.post(f"/pdc-cheques/{first['id']}/bounce", {"reason": "Returned"}).status_code == 200
    ks = kinds(api)
    assert "cheque_bounced" in ks and "cheque_overdue" not in ks
    sev = {a["kind"]: a["severity"] for a in alerts(api)}
    assert sev["cheque_bounced"] == "critical"


def test_supplier_dues_alert(funded, bid, admin) -> None:
    api = funded
    sid = admin.execute(
        "insert into public.suppliers (name) values ('Clean Chem Trading') returning id"
    ).fetchone()[0]
    admin.execute(
        "insert into public.supplier_entries (supplier_id, entry_date, kind, amount, reference) "
        "values (%s, %s, 'due', 750.00, 'INV-1')",
        (sid, TODAY),
    )
    a = of(api, "supplier_dues")
    admin.execute("delete from public.supplier_entries")
    admin.execute("delete from public.suppliers where id=%s", (sid,))
    assert len(a) == 1 and a[0]["severity"] == "info" and "750.00" in a[0]["detail"]
    assert a[0]["href"] == f"/suppliers/{sid}"
    assert of(api, "supplier_dues") == []


def test_summary_counts_match_list_and_dashboard(api, bid) -> None:
    task(api, bid, "A", due_date=d(-1))
    task(api, bid, "B", due_date=d(0))
    task(api, bid, "C", due_date=d(4))
    s = api.get("/alerts/summary").json()
    items = alerts(api)
    assert s["total_active"] == len(items) == 3
    assert (s["critical"], s["warning"], s["info"]) == (0, 2, 1)
    assert s["critical"] + s["warning"] + s["info"] == s["total_active"]
    assert s["unread"] == 3 and len(s["recent"]) == 3 and s["by_module"]["tasks"] == 3
    # most important first: warnings before the informational one
    assert [a["severity"] for a in s["recent"]] == ["warning", "warning", "info"]
    keys = {a["key"]: a["count"] for a in api.get("/dashboard/owner").json()["alerts"]}
    assert keys["tasks_overdue"] == 1 and keys["tasks_due_today"] == 1 and keys["tasks_due_7"] == 1


def test_filters_search_and_pagination(api, bid) -> None:
    for i in range(7):
        task(api, bid, f"Task {i}", due_date=d(-1 - i))
    task(api, bid, "Soon", due_date=d(2))
    assert api.get("/alerts", severity="info").json()["total"] == 1
    assert api.get("/alerts", severity="critical").json()["total"] == 0
    assert api.get("/alerts", module="tasks").json()["total"] == 8
    assert (
        api.get("/alerts", kind="task_overdue", page_size=3, page=3).json()["items"].__len__() == 1
    )
    assert api.get("/alerts", q="soon").json()["total"] == 1
    assert api.get("/alerts", branch_id=str(bid["ALSAFA MAIN"])).json()["total"] == 8
    assert api.get("/alerts", status="unread").json()["total"] == 8
    assert api.get("/alerts", severity="bogus").status_code == 422
    f = api.get("/alerts/facets").json()
    assert ["task_overdue", "Task overdue"] in f["kinds"] and ["tasks", "Tasks"] in f["modules"]


def test_alerts_are_owner_only(api, bid, client) -> None:
    t = task(api, bid, due_date=d(-1))
    a = alerts(api)[0]
    for path in (
        "/alerts",
        "/alerts/summary",
        "/alerts/unread-count",
        "/alerts/history",
        "/alerts/facets",
    ):
        assert api.get(path, who="branch").status_code == 403, path
    for path in (
        "/alerts/refresh",
        "/alerts/read-all",
        f"/alerts/{a['id']}/read",
        f"/alerts/{a['id']}/acknowledge",
    ):
        assert api.post(path, who="branch").status_code == 403, path
        assert client.post(f"{API}{path}").status_code == 401, path
    assert t and api.get("/alerts/summary").json()["unread"] == 1  # untouched by the denied calls
