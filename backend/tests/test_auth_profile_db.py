"""DB-backed auth tests: real PostgreSQL, real Step 2 migrations + RLS, connecting as the restricted `app_api`
role exactly like production. Only the Supabase-managed parts (auth.users, auth.uid(), roles) are the Step 2 stub,
and tokens are signed by locally generated keys -- see docs/authentication/AUTH_TEST_RESULTS.md."""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.security import TokenClaims, TokenVerifier
from app.database.session import Database
from app.main import create_app
from tests.conftest import make_settings
from tests.jwt_helpers import FakeJwks, KeyPair, claims

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def key() -> KeyPair:
    return KeyPair("kid-db")


@pytest.fixture(scope="module")
def world(pg_admin_dsn: str) -> dict[str, uuid.UUID]:
    """Owner, two branch users (different branches), one inactive branch user, one user without a profile."""
    ids = {n: uuid.uuid4() for n in ("owner", "branch_a", "branch_b", "inactive", "no_profile")}
    with psycopg.connect(pg_admin_dsn, autocommit=True) as c:
        branches = [
            r[0]
            for r in c.execute("select id from public.branches order by sort_order, name limit 2")
        ]
        ids["branch_a_branch"], ids["branch_b_branch"] = branches
        for n in ("owner", "branch_a", "branch_b", "inactive", "no_profile"):
            c.execute(
                "insert into auth.users (id, email) values (%s, %s)", (ids[n], f"{n}@example.test")
            )
        c.execute(
            "insert into public.profiles (user_id, full_name, role) values (%s,'Test Owner','owner')",
            (ids["owner"],),
        )
        c.execute(
            "insert into public.profiles (user_id, full_name, role, branch_id) values (%s,'Branch A','branch',%s)",
            (ids["branch_a"], branches[0]),
        )
        c.execute(
            "insert into public.profiles (user_id, full_name, role, branch_id) values (%s,'Branch B','branch',%s)",
            (ids["branch_b"], branches[1]),
        )
        c.execute(
            "insert into public.profiles (user_id, full_name, role, branch_id, is_active) values (%s,'Gone','branch',%s,false)",
            (ids["inactive"], branches[0]),
        )
    return ids


@pytest.fixture()
def client(app_api_url: str, key: KeyPair) -> Iterator[TestClient]:
    settings = make_settings(supabase_url="https://abcd.supabase.test", database_url=app_api_url)
    app = create_app(settings)
    app.state.token_verifier = TokenVerifier(settings, fetcher=FakeJwks(key))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def auth(key: KeyPair, uid: uuid.UUID, **over: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {key.sign(claims(uid, **over))}"}


def test_connects_as_restricted_role(app_api_url: str) -> None:
    with psycopg.connect(app_api_url) as c:
        user, bypass, sup = c.execute(
            "select current_user, r.rolbypassrls, r.rolsuper from pg_roles r where r.rolname = current_user"
        ).fetchone()
    assert (user, bypass, sup) == ("app_api", False, False)


def test_owner_profile(client, key, world) -> None:
    r = client.get("/api/v1/auth/profile", headers=auth(key, world["owner"]))
    assert r.status_code == 200, r.text
    body = r.json()
    perms = body.pop("permissions")
    assert body == {
        "user_id": str(world["owner"]),
        "full_name": "Test Owner",
        "role": "owner",
        "branch_id": None,
        "branch_name": None,
        "is_active": True,
    }
    assert perms["user_management"]["scope"] == "all_branches"


def test_branch_user_profile_includes_branch(client, key, world) -> None:
    r = client.get("/api/v1/auth/profile", headers=auth(key, world["branch_a"]))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "branch" and body["branch_id"] == str(world["branch_a_branch"])
    assert body["branch_name"]


def test_missing_profile_is_403(client, key, world) -> None:
    r = client.get("/api/v1/auth/profile", headers=auth(key, world["no_profile"]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "profile_missing"


def test_unknown_user_is_403_not_500(client, key) -> None:
    r = client.get("/api/v1/auth/profile", headers=auth(key, uuid.uuid4()))
    assert r.status_code == 403 and r.json()["error"]["code"] == "profile_missing"


def test_inactive_account_is_403(client, key, world) -> None:
    r = client.get("/api/v1/auth/profile", headers=auth(key, world["inactive"]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_inactive"


def test_me_is_token_only_and_works_without_profile(client, key, world) -> None:
    assert client.get("/api/v1/auth/me", headers=auth(key, world["no_profile"])).status_code == 200


def test_token_metadata_cannot_grant_role_or_branch(client, key, world) -> None:
    hostile = {
        "role": "authenticated",
        "user_metadata": {"role": "owner", "branch_id": str(uuid.uuid4())},
        "app_metadata": {"role": "owner"},
    }
    r = client.get("/api/v1/auth/profile", headers=auth(key, world["branch_a"], **hostile))
    assert r.json()["role"] == "branch"
    assert r.json()["branch_id"] == str(world["branch_a_branch"])


def test_no_endpoint_accepts_role_changes(client, key, world) -> None:
    h = auth(key, world["branch_a"])
    for method in ("put", "patch", "post", "delete"):
        r = client.request(
            method.upper(), "/api/v1/auth/profile", headers=h, json={"role": "owner"}
        )
        assert r.status_code in (404, 405)
    for path in ("/api/v1/auth/logout", "/api/v1/auth/register", "/api/v1/auth/signup"):
        assert client.post(path, headers=h).status_code == 404


def _claims(uid: uuid.UUID) -> TokenClaims:
    return TokenClaims(
        user_id=uid, email=None, session_id=None, issued_at=None, expires_at=9999999999, aal=None
    )


@pytest.fixture()
def db(app_api_url: str) -> Iterator[Database]:
    d = Database(make_settings(database_url=app_api_url))
    yield d
    d.dispose()


def _session(db: Database, uid: uuid.UUID):
    gen = db.session_for(_claims(uid))
    return gen, next(gen)


def test_session_runs_as_authenticated_with_caller_uid(db, world) -> None:
    gen, s = _session(db, world["branch_a"])
    row = s.execute(text("select current_user, auth.uid(), app.user_role()")).one()
    assert (row[0], row[1], row[2]) == ("authenticated", world["branch_a"], "branch")
    gen.close()


def test_rls_context_survives_commit_and_rollback(db, world) -> None:
    gen, s = _session(db, world["branch_a"])
    s.execute(text("select 1"))
    s.commit()
    assert s.execute(text("select current_user, auth.uid()")).one() == (
        "authenticated",
        world["branch_a"],
    )
    s.rollback()
    assert s.execute(text("select current_user, auth.uid()")).one() == (
        "authenticated",
        world["branch_a"],
    )
    gen.close()


def test_context_does_not_leak_to_next_checkout(db, world) -> None:
    gen, s = _session(db, world["owner"])
    s.execute(text("select 1"))
    gen.close()
    with db.engine.connect() as conn:  # pooled connection, plain use
        row = conn.execute(
            text("select current_user, current_setting('request.jwt.claims', true)")
        ).one()
    assert row[0] == "app_api" and not row[1]


def test_branch_user_sees_only_own_profile(db, world) -> None:
    gen, s = _session(db, world["branch_a"])
    ids = {r[0] for r in s.execute(text("select user_id from public.profiles"))}
    assert ids == {world["branch_a"]}
    gen.close()


def test_owner_sees_all_profiles(db, world) -> None:
    gen, s = _session(db, world["owner"])
    assert (
        s.execute(text("select count(*) from public.profiles")).scalar_one() == 4
    )  # owner, two branch users, one inactive
    gen.close()


def test_user_cannot_escalate_own_role_through_the_api_session(db, world, pg_admin_dsn) -> None:
    gen, s = _session(db, world["branch_a"])
    res = s.execute(
        text("update public.profiles set role='owner', branch_id=null where user_id=:u"),
        {"u": world["branch_a"]},
    )
    assert res.rowcount == 0  # RLS: profiles_update_owner hides the row from a non-owner
    s.commit()
    with pytest.raises(DBAPIError):
        s.execute(
            text("insert into public.profiles (user_id, full_name, role) values (:u,'x','owner')"),
            {"u": world["no_profile"]},
        )
        s.commit()
    gen.close()
    with psycopg.connect(pg_admin_dsn) as c:
        assert (
            c.execute(
                "select role from public.profiles where user_id=%s", (world["branch_a"],)
            ).fetchone()[0]
            == "branch"
        )
        assert (
            c.execute(
                "select count(*) from public.profiles where user_id=%s", (world["no_profile"],)
            ).fetchone()[0]
            == 0
        )


def test_inactive_user_gets_no_data_under_rls(db, world) -> None:
    gen, s = _session(db, world["inactive"])
    assert s.execute(text("select app.user_role()")).scalar_one() is None
    assert s.execute(text("select count(*) from public.branches")).scalar_one() == 0
    gen.close()


def test_backend_without_database_returns_503(key, world) -> None:
    settings = make_settings(supabase_url="https://abcd.supabase.test")
    app = create_app(settings)
    app.state.token_verifier = TokenVerifier(settings, fetcher=FakeJwks(key))
    r = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/auth/profile", headers=auth(key, world["owner"])
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_not_configured"
