"""API + database RBAC tests (Step 5). Real FastAPI app, real PostgreSQL with migrations 0001-0010 and RLS,
connecting as the restricted `app_api` role; tokens signed with locally generated keys.
Numbers in test names refer to the 16 security test cases of the Step 5 brief."""

import json
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Annotated

import psycopg
import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.authz import BranchScope, get_branch_scope
from app.api.deps import DbSession
from app.core.exceptions import NotFoundError
from app.core.permissions import Action, Module
from app.core.security import TokenClaims, TokenVerifier
from app.database.session import Database
from app.main import create_app
from tests.conftest import make_settings
from tests.jwt_helpers import FakeJwks, KeyPair, claims

pytestmark = pytest.mark.integration

BRANCHES = [
    "ALSAFA MAIN",
    "JERNAS",
    "SATWA",
    "BURDUBAI",
    "NDL",
    "AL BARSHA",
    "MIRDIF",
    "AL JADDAF",
    "KARAMA",
    "SALES TEAM",
]


# ---- test-only routes: stand-ins for future business endpoints, to prove the reusable guards ---------------
probe_router = APIRouter(prefix="/__test")


@probe_router.get("/reports")
def list_reports(
    session: DbSession,
    scope: Annotated[BranchScope, Depends(get_branch_scope(Module.DAILY_REPORTS, Action.READ))],
    branch_id: uuid.UUID | None = None,
) -> list[str]:
    stmt = "select id::text from public.daily_reports"
    b = scope.resolve(branch_id)
    rows = session.execute(
        text(stmt + (" where branch_id = :b" if b else "")), {"b": b} if b else {}
    )
    return [r[0] for r in rows]


@probe_router.get("/reports/{report_id}")
def get_report_guarded(
    report_id: uuid.UUID,
    session: DbSession,
    scope: Annotated[BranchScope, Depends(get_branch_scope(Module.DAILY_REPORTS, Action.READ))],
) -> dict[str, str]:
    row = session.execute(
        text("select id::text, branch_id from public.daily_reports where id=:i"), {"i": report_id}
    ).first()
    if row is None:
        raise NotFoundError(
            "Report not found"
        )  # RLS hides other branches' rows: same answer as "does not exist"
    scope.ensure(row[1])  # belt and braces: the loaded record's branch must be allowed
    return {"id": row[0]}


@probe_router.get("/unsafe-reports/{report_id}")
def get_report_unsafe(report_id: uuid.UUID, session: DbSession) -> dict[str, str]:
    """A handler that FORGOT its branch check. Only RLS stands between the caller and the data."""
    row = session.execute(
        text("select id::text from public.daily_reports where id=:i"), {"i": report_id}
    ).first()
    return {"id": row[0] if row else "none"}


class Body(BaseModel):
    branch_id: uuid.UUID


@probe_router.post("/reports")
def post_report(
    body: Body,
    scope: Annotated[BranchScope, Depends(get_branch_scope(Module.DAILY_REPORTS, Action.CREATE))],
) -> dict[str, str]:
    return {"branch_id": str(scope.ensure(body.branch_id))}


# ---- fixtures ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def key() -> KeyPair:
    return KeyPair("kid-rbac")


@pytest.fixture(scope="module")
def branch_ids(pg_admin_dsn: str) -> dict[str, uuid.UUID]:
    with psycopg.connect(pg_admin_dsn) as c:
        return {n: i for i, n in c.execute("select id, name from public.branches")}


@pytest.fixture(scope="module")
def admin(pg_admin_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_admin_dsn, autocommit=True) as c:
        yield c


class Users:
    def __init__(self, admin: psycopg.Connection, branches: dict[str, uuid.UUID]) -> None:
        self.admin, self.branches = admin, branches

    def make(
        self, role: str, branch: str | None = None, *, active: bool = True, profile: bool = True
    ) -> uuid.UUID:
        uid = uuid.uuid4()
        self.admin.execute(
            "insert into auth.users (id, email) values (%s,%s)",
            (uid, f"{uid.hex[:10]}@example.test"),
        )
        if profile:
            self.admin.execute(
                "insert into public.profiles (user_id, full_name, role, branch_id, is_active) values (%s,%s,%s,%s,%s)",
                (
                    uid,
                    f"{role} {branch or ''}".strip(),
                    role,
                    self.branches[branch] if branch else None,
                    active,
                ),
            )
        return uid

    def report(self, branch: str) -> uuid.UUID:
        # A distinct date per report: (branch, date) is unique for active reports, so random dates collided.
        self._day = getattr(self, "_day", 0) + 1
        rid = self.admin.execute(
            """insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received)
               values (%s, %s, 100, 1, 100) returning id""",
            (date(2026, 1, 1) + timedelta(days=self._day), self.branches[branch]),
        ).fetchone()[0]
        return rid


@pytest.fixture(scope="module")
def users(admin, branch_ids) -> Users:
    return Users(admin, branch_ids)


@pytest.fixture(scope="module")
def owner(users) -> uuid.UUID:
    return users.make("owner")


@pytest.fixture(scope="module")
def main_user(users) -> uuid.UUID:
    return users.make("branch", "ALSAFA MAIN")


@pytest.fixture(scope="module")
def jernas_user(users) -> uuid.UUID:
    return users.make("branch", "JERNAS")


@pytest.fixture()
def client(app_api_url: str, key: KeyPair) -> Iterator[TestClient]:
    settings = make_settings(supabase_url="https://abcd.supabase.test", database_url=app_api_url)
    app = create_app(settings)
    app.state.token_verifier = TokenVerifier(settings, fetcher=FakeJwks(key))
    app.include_router(probe_router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def hdr(key: KeyPair, uid: uuid.UUID, **over: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {key.sign(claims(uid, **over))}"}


def code(resp) -> str:
    return resp.json()["error"]["code"]


# ---- 1. owner can access all ten branches ----------------------------------------------------------------
def test_01_owner_sees_all_ten_branches(client, key, owner, branch_ids) -> None:
    r = client.get("/api/v1/branches", headers=hdr(key, owner))
    assert r.status_code == 200
    assert [b["name"] for b in r.json()] == BRANCHES
    for name, bid in branch_ids.items():
        assert client.get(f"/api/v1/branches/{bid}", headers=hdr(key, owner)).json()["name"] == name


def test_01_owner_can_filter_one_branch_and_unknown_id_is_404(
    client, key, owner, branch_ids
) -> None:
    r = client.get(
        "/api/v1/branches", params={"branch_id": str(branch_ids["SATWA"])}, headers=hdr(key, owner)
    )
    assert [b["name"] for b in r.json()] == ["SATWA"]
    assert (
        client.get(f"/api/v1/branches/{uuid.uuid4()}", headers=hdr(key, owner)).status_code == 404
    )


# ---- 2. branch user can access the assigned branch -------------------------------------------------------
def test_02_branch_user_sees_only_assigned_branch(client, key, main_user, branch_ids) -> None:
    r = client.get("/api/v1/branches", headers=hdr(key, main_user))
    assert [b["name"] for b in r.json()] == ["ALSAFA MAIN"]
    assert (
        client.get(
            f"/api/v1/branches/{branch_ids['ALSAFA MAIN']}", headers=hdr(key, main_user)
        ).status_code
        == 200
    )
    own = client.get(
        "/api/v1/branches",
        params={"branch_id": str(branch_ids["ALSAFA MAIN"])},
        headers=hdr(key, main_user),
    )
    assert own.status_code == 200


# ---- 3. branch user cannot access another branch (path, query, body, record id) --------------------------
def test_03_other_branch_by_path(client, key, main_user, branch_ids) -> None:
    r = client.get(f"/api/v1/branches/{branch_ids['JERNAS']}", headers=hdr(key, main_user))
    assert r.status_code == 403 and code(r) == "branch_access_denied"


def test_03_other_branch_by_query(client, key, main_user, branch_ids) -> None:
    for path in ("/api/v1/branches", "/__test/reports"):
        r = client.get(
            path, params={"branch_id": str(branch_ids["JERNAS"])}, headers=hdr(key, main_user)
        )
        assert r.status_code == 403 and code(r) == "branch_access_denied", path


def test_03_other_branch_by_body(client, key, main_user, branch_ids) -> None:
    r = client.post(
        "/__test/reports",
        json={"branch_id": str(branch_ids["JERNAS"])},
        headers=hdr(key, main_user),
    )
    assert r.status_code == 403 and code(r) == "branch_access_denied"
    ok = client.post(
        "/__test/reports",
        json={"branch_id": str(branch_ids["ALSAFA MAIN"])},
        headers=hdr(key, main_user),
    )
    assert ok.status_code == 200


def test_03_nonexistent_and_other_branch_look_identical(client, key, main_user, branch_ids) -> None:
    a = client.get(f"/api/v1/branches/{branch_ids['JERNAS']}", headers=hdr(key, main_user))
    b = client.get(f"/api/v1/branches/{uuid.uuid4()}", headers=hdr(key, main_user))
    assert (a.status_code, code(a)) == (b.status_code, code(b)) == (403, "branch_access_denied")


def test_03_malformed_branch_id_is_refused(client, key, main_user) -> None:
    r = client.get("/api/v1/branches/not-a-uuid", headers=hdr(key, main_user))
    assert r.status_code in (403, 422)


def test_03_branch_list_never_leaks_other_branches(client, key, main_user) -> None:
    text_ = client.get("/api/v1/branches", headers=hdr(key, main_user)).text
    assert "JERNAS" not in text_ and "SATWA" not in text_


# ---- 4/5. no way to change own role or branch -----------------------------------------------------------
def test_04_05_no_api_route_changes_roles_or_branches(client, key, main_user, branch_ids) -> None:
    h = hdr(key, main_user)
    body = {"role": "owner", "branch_id": str(branch_ids["JERNAS"]), "user_id": str(main_user)}
    for method in ("PUT", "PATCH", "POST", "DELETE"):
        for path in ("/api/v1/auth/profile", f"/api/v1/users/{main_user}", "/api/v1/users"):
            assert client.request(method, path, headers=h, json=body).status_code in (
                403,
                404,
                405,
            ), (method, path)


def test_04_05_database_refuses_self_change_through_the_api_session(
    app_api_url, main_user, branch_ids, admin
) -> None:
    db = Database(make_settings(database_url=app_api_url))
    gen = db.session_for(TokenClaims(main_user, None, None, None, 9999999999, None))
    s = next(gen)
    for sql in (
        "update public.profiles set role='owner' where user_id=:u",
        "update public.profiles set branch_id=:b where user_id=:u",
        "update public.profiles set is_active=false where user_id=:u",
    ):
        assert s.execute(text(sql), {"u": main_user, "b": branch_ids["JERNAS"]}).rowcount == 0
    gen.close()
    db.dispose()
    row = admin.execute(
        "select role, branch_id, is_active from public.profiles where user_id=%s", (main_user,)
    ).fetchone()
    assert row == ("branch", branch_ids["ALSAFA MAIN"], True)


def test_04_05_token_metadata_and_headers_cannot_grant_owner(client, key, main_user) -> None:
    hostile = {
        "user_metadata": {"role": "owner"},
        "app_metadata": {"role": "owner", "branch_id": str(uuid.uuid4())},
    }
    h = {
        **hdr(key, main_user, **hostile),
        "X-Role": "owner",
        "X-User-Role": "owner",
        "X-Branch-Id": str(uuid.uuid4()),
    }
    r = client.get("/api/v1/users", headers=h)
    assert r.status_code == 403 and code(r) == "permission_denied"
    assert client.get("/api/v1/auth/profile", headers=h).json()["role"] == "branch"
    assert (
        client.get(
            "/api/v1/users", params={"role": "owner", "as_user": str(uuid.uuid4())}, headers=h
        ).status_code
        == 403
    )


# ---- 6. inactive account denied ---------------------------------------------------------------------------
def test_06_inactive_account_denied_everywhere(client, key, users) -> None:
    for role, branch in (("branch", "ALSAFA MAIN"), ("owner", None)):
        uid = users.make(role, branch, active=False)
        for path in (
            "/api/v1/branches",
            "/api/v1/users",
            "/api/v1/auth/profile",
            "/__test/reports",
        ):
            r = client.get(path, headers=hdr(key, uid))
            assert r.status_code == 403 and code(r) == "account_inactive", (role, path)


def test_06_user_without_profile_denied(client, key, users) -> None:
    uid = users.make("branch", profile=False)
    r = client.get("/api/v1/branches", headers=hdr(key, uid))
    assert r.status_code == 403 and code(r) == "profile_missing"


# ---- 7/8. anonymous and invalid JWT -----------------------------------------------------------------------
@pytest.mark.parametrize(
    "path", ["/api/v1/branches", "/api/v1/users", "/api/v1/auth/profile", "/__test/reports"]
)
def test_07_anonymous_denied(client, path) -> None:
    r = client.get(path)
    assert r.status_code == 401 and code(r) == "not_authenticated"


def test_08_invalid_jwt_denied(client, key, owner) -> None:
    other = KeyPair("kid-rbac")  # same kid, different key
    for tok in (
        "garbage",
        other.sign(claims(owner)),
        key.sign(claims(owner, aud="x")),
        key.sign(claims(owner, exp=1)),
    ):
        r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401, tok[:20]


# ---- 9/11. owner-only API rejects branch users with 403 ------------------------------------------------
def test_09_owner_only_api_rejects_branch_user(client, key, main_user, owner) -> None:
    for path in ("/api/v1/users", f"/api/v1/users/{owner}", f"/api/v1/users/{main_user}"):
        r = client.get(path, headers=hdr(key, main_user))
        assert r.status_code == 403 and code(r) == "permission_denied", path
    assert client.get("/api/v1/users", headers=hdr(key, owner)).status_code == 200


def test_09_owner_user_listing_excludes_secrets(client, key, owner) -> None:
    body = client.get("/api/v1/users", headers=hdr(key, owner)).json()
    assert body and set(body[0]) == {
        "user_id",
        "full_name",
        "role",
        "branch_id",
        "is_active",
        "created_at",
    }


def test_11_denials_are_403_json_with_request_id(client, key, main_user) -> None:
    r = client.get("/api/v1/users", headers=hdr(key, main_user))
    assert r.status_code == 403
    assert r.json()["error"]["message"] == "You do not have permission to do this."
    assert r.json()["request_id"]


# ---- 12. direct record-ID access cannot bypass branch restrictions -----------------------------------------
def test_12_direct_record_id_guarded_handler(client, key, main_user, owner, users) -> None:
    other = users.report("JERNAS")
    own = users.report("ALSAFA MAIN")
    r = client.get(f"/__test/reports/{other}", headers=hdr(key, main_user))
    assert (
        r.status_code == 404 and code(r) == "not_found"
    )  # RLS hides it: indistinguishable from a missing id
    assert (
        client.get(f"/__test/reports/{uuid.uuid4()}", headers=hdr(key, main_user)).status_code
        == 404
    )
    assert client.get(f"/__test/reports/{own}", headers=hdr(key, main_user)).json() == {
        "id": str(own)
    }
    assert client.get(f"/__test/reports/{other}", headers=hdr(key, owner)).json() == {
        "id": str(other)
    }


def test_12_even_a_handler_without_a_check_cannot_leak_thanks_to_rls(
    client, key, main_user, owner, users
) -> None:
    other = users.report("JERNAS")
    r = client.get(f"/__test/unsafe-reports/{other}", headers=hdr(key, main_user))
    assert r.json() == {"id": "none"}  # RLS hides the row entirely
    assert client.get(f"/__test/unsafe-reports/{other}", headers=hdr(key, owner)).json() == {
        "id": str(other)
    }


def test_12_list_is_scoped(client, key, main_user, jernas_user, users) -> None:
    mine, theirs = users.report("ALSAFA MAIN"), users.report("JERNAS")
    ids = client.get("/__test/reports", headers=hdr(key, main_user)).json()
    assert str(mine) in ids and str(theirs) not in ids
    ids = client.get("/__test/reports", headers=hdr(key, jernas_user)).json()
    assert str(theirs) in ids and str(mine) not in ids


# ---- 13/14. submitted reports cannot be edited or deleted -------------------------------------------------
def test_13_14_no_edit_or_delete_route_exists(client, key, main_user, owner, users) -> None:
    rid = users.report("ALSAFA MAIN")
    for who in (main_user, owner):
        for method in ("PUT", "PATCH", "DELETE"):
            for path in (f"/__test/reports/{rid}", f"/api/v1/daily-reports/{rid}"):
                assert client.request(
                    method, path, headers=hdr(key, who), json={"total_sales": 1}
                ).status_code in (404, 405)


def test_13_14_database_refuses_edit_and_delete_even_through_the_api_role(
    app_api_url, main_user, owner, users, admin
) -> None:
    rid = users.report("ALSAFA MAIN")
    db = Database(make_settings(database_url=app_api_url))
    for who in (main_user, owner):
        for sql in (
            "update public.daily_reports set total_sales=1 where id=:i",
            "delete from public.daily_reports where id=:i",
        ):
            gen = db.session_for(TokenClaims(who, None, None, None, 9999999999, None))
            s = next(gen)
            with pytest.raises(DBAPIError):
                s.execute(text(sql), {"i": rid})
            gen.close()
    db.dispose()
    assert (
        admin.execute(
            "select total_sales from public.daily_reports where id=%s", (rid,)
        ).fetchone()[0]
        == 100
    )


# ---- 15. RLS blocks unauthorized queries made through the API role ----------------------------------------
def test_15_rls_blocks_raw_queries_in_a_branch_session(
    app_api_url, main_user, users, admin
) -> None:
    admin.execute("insert into public.suppliers (name) values ('RLS-probe')")
    users.report("JERNAS")
    db = Database(make_settings(database_url=app_api_url))
    gen = db.session_for(TokenClaims(main_user, None, None, None, 9999999999, None))
    s = next(gen)
    for t in (
        "suppliers",
        "employees",
        "tasks",
        "opening_balances",
        "rental_agreements",
        "pdc_cheques",
        "audit_log",
    ):
        assert s.execute(text(f"select count(*) from public.{t}")).scalar_one() == 0, t
    assert s.execute(text("select count(*) from public.branches")).scalar_one() == 1
    assert (
        s.execute(
            text("select count(*) from public.daily_reports where branch_id <> app.branch_id()")
        ).scalar_one()
        == 0
    )
    gen.close()
    db.dispose()


# ---- 16. permission checks work after session refresh -------------------------------------------------------
def test_16_refreshed_token_keeps_same_permissions(client, key, main_user, owner) -> None:
    for _ in range(3):  # a refresh = a brand-new token (new iat/session) for the same user
        assert client.get("/api/v1/users", headers=hdr(key, main_user)).status_code == 403
        assert client.get("/api/v1/users", headers=hdr(key, owner)).status_code == 200


def test_16_role_change_takes_effect_on_the_next_request_with_the_same_token(
    client, key, users, admin
) -> None:
    uid = users.make("owner")
    h = hdr(key, uid)  # one token, used before and after the change
    assert client.get("/api/v1/users", headers=h).status_code == 200
    admin.execute(
        "update public.profiles set role='branch', branch_id=%s where user_id=%s",
        (users.branches["SATWA"], uid),
    )
    assert client.get("/api/v1/users", headers=h).status_code == 403
    assert [b["name"] for b in client.get("/api/v1/branches", headers=h).json()] == ["SATWA"]
    assert (
        client.get("/api/v1/auth/profile", headers=h).json()["permissions"].get("user_management")
        is None
    )


def test_16_deactivation_takes_effect_on_the_next_request_with_the_same_token(
    client, key, users, admin
) -> None:
    uid = users.make("branch", "MIRDIF")
    h = hdr(key, uid)
    assert client.get("/api/v1/branches", headers=h).status_code == 200
    admin.execute("update public.profiles set is_active=false where user_id=%s", (uid,))
    r = client.get("/api/v1/branches", headers=h)
    assert r.status_code == 403 and code(r) == "account_inactive"


# ---- permissions payload for the UI ---------------------------------------------------------------------------
def test_profile_includes_permission_slice(client, key, owner, main_user) -> None:
    o = client.get("/api/v1/auth/profile", headers=hdr(key, owner)).json()["permissions"]
    b = client.get("/api/v1/auth/profile", headers=hdr(key, main_user)).json()["permissions"]
    assert set(o) >= {"user_management", "suppliers", "employees", "settings"}
    assert set(b) == {
        "dashboard",
        "branch_management",
        "daily_reports",
        "orders",
        "customers",
        "order_payments",
    }
    assert b["daily_reports"] == {"actions": ["create", "read"], "scope": "own_branch"}


# ---- audit of failed privileged access ---------------------------------------------------------------------------
def test_denied_attempts_are_audited_without_secrets(client, key, users, admin, branch_ids) -> None:
    uid = users.make("branch", "NDL")
    h = hdr(key, uid)
    client.get("/api/v1/users", headers=h)
    client.get(f"/api/v1/branches/{branch_ids['JERNAS']}", headers=h)
    rows = admin.execute(
        "select new_values, action, table_name from public.audit_log where actor_user_id=%s and action='ACCESS_DENIED' order by id",
        (uid,),
    ).fetchall()
    assert [r[0]["module"] for r in rows] == ["user_management", "branch_management"]
    assert rows[1][0]["action"] == "branch_access" and rows[1][0]["detail"][
        "requested_branch"
    ] == str(branch_ids["JERNAS"])
    dump = json.dumps(rows, default=str).lower()
    assert "bearer" not in dump and "token" not in dump and "password" not in dump


def test_allowed_requests_are_not_logged_as_denied(client, key, users, admin) -> None:
    uid = users.make("branch", "KARAMA")
    client.get("/api/v1/branches", headers=hdr(key, uid))
    n = admin.execute(
        "select count(*) from public.audit_log where actor_user_id=%s and action='ACCESS_DENIED'",
        (uid,),
    ).fetchone()[0]
    assert n == 0


def test_anonymous_denials_are_not_written_to_the_database(client, admin) -> None:
    before = admin.execute(
        "select count(*) from public.audit_log where action='ACCESS_DENIED'"
    ).fetchone()[0]
    client.get("/api/v1/users")
    after = admin.execute(
        "select count(*) from public.audit_log where action='ACCESS_DENIED'"
    ).fetchone()[0]
    assert before == after
