#!/usr/bin/env python3
"""Local end-to-end run: real React app + real FastAPI + real PostgreSQL (Step 2 migrations, RLS, `app_api` role)
+ SIMULATED Supabase Auth (e2e/fake_gotrue.py), driven by Playwright in system Chrome.

>>> The Auth server is a simulation. This proves OUR code against the GoTrue protocol; it does NOT prove the
>>> behaviour of a real Supabase project (email delivery, dashboard settings, real key rotation). <<<

Run from the repo root:  backend/.venv/bin/python e2e/run_e2e.py
Needs: a disposable PostgreSQL superuser (TEST_PG_ADMIN_DSN), `pip install playwright`, Chrome at /usr/bin/google-chrome
(or CHROME_PATH), `npm ci` in frontend/.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import secrets
import signal
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable

import psycopg
from playwright.sync_api import Browser, BrowserContext, Page, expect, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADMIN_DSN = os.environ.get(
    "TEST_PG_ADMIN_DSN", "host=/tmp port=54329 user=postgres dbname=postgres"
)
CHROME = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")
AUTH, API, WEB = "http://localhost:54321", "http://localhost:8000", "http://localhost:5173"
SERVICE_KEY = "e2e-service-role-key-not-real"
PY = sys.executable
APP_API_PW = "e2e-" + secrets.token_hex(8)
procs: list[subprocess.Popen] = []
results: list[tuple[str, bool, str]] = []


def http(
    method: str, url: str, body: dict | None = None, headers: dict | None = None
) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}


def wait_for(url: str, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"timed out waiting for {url}")


def spawn(cmd: list[str], cwd: pathlib.Path, env: dict[str, str], log: str) -> None:
    f = open(f"/tmp/e2e_{log}.log", "w")
    procs.append(
        subprocess.Popen(
            cmd,
            cwd=cwd,
            env={**os.environ, **env},
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    )


def stop_all() -> None:
    for p in procs:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(p.pid, signal.SIGTERM)


def scenario(name: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        def run(*a, **k) -> None:
            try:
                fn(*a, **k)
                results.append((name, True, ""))
                print(f"PASS  {name}", flush=True)
            except Exception as exc:  # noqa: BLE001
                results.append(
                    (
                        name,
                        False,
                        f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}",
                    )
                )
                print(f"FAIL  {name}\n      {traceback.format_exc(limit=3)}", flush=True)

        return run

    return deco


def sign_in_token(email: str, password: str) -> str:
    status, body = http(
        "POST", f"{AUTH}/auth/v1/token?grant_type=password", {"email": email, "password": password}
    )
    assert status == 200, body
    return body["access_token"]


def login_ui(page: Page, email: str, password: str, remember: bool = True) -> None:
    page.goto(f"{WEB}/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    if not remember:
        page.get_by_label("Keep me signed in on this device").uncheck()
    page.get_by_role("button", name="Sign in").click()


def main() -> int:
    admin = psycopg.connect(ADMIN_DSN, autocommit=True)
    dbname = f"alsafa_e2e_{uuid.uuid4().hex[:8]}"
    admin.execute(f'create database "{dbname}"')
    dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={dbname}")
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute((ROOT / "database/tests/stub_supabase.sql").read_text())
            for m in sorted((ROOT / "database/migrations").glob("*.sql")):
                c.execute(m.read_text())
            c.execute(f"alter role app_api login password '{APP_API_PW}'")
        app_url = f"postgresql://app_api:{APP_API_PW}@/{dbname}?host=/tmp&port=54329"

        spawn([PY, "e2e/fake_gotrue.py", "54321"], ROOT, {"FAKE_AUTH_DB_DSN": dsn}, "auth")
        spawn(
            [PY, "-m", "uvicorn", "app.main:app", "--port", "8000", "--log-level", "warning"],
            ROOT / "backend",
            {
                "APP_ENV": "development",
                "SUPABASE_URL": AUTH,
                "DATABASE_URL": app_url,
                "CORS_ORIGINS": WEB,
                "JWKS_REFRESH_COOLDOWN_SECONDS": "1",
                "JWKS_CACHE_TTL_SECONDS": "2",
                "LOG_LEVEL": "WARNING",
            },
            "api",
        )
        spawn(
            ["npx", "vite", "--host", "localhost"],
            ROOT / "frontend",
            {
                "VITE_API_BASE_URL": f"{API}/api/v1",
                "VITE_SUPABASE_URL": AUTH,
                "VITE_SUPABASE_ANON_KEY": "e2e-anon-key-not-real",
            },
            "web",
        )
        wait_for(f"{AUTH}/auth/v1/.well-known/jwks.json")
        wait_for(f"{API}/api/v1/health")
        wait_for(WEB)

        with psycopg.connect(dsn, autocommit=True) as c:
            b1, b2 = [
                r[0:2]
                for r in c.execute(
                    "select id, name from public.branches order by sort_order, name limit 2"
                )
            ]
        users = {}
        for key, email, pw in [
            ("owner", "owner@e2e.test", "OwnerPass123"),
            ("branch", "branch@e2e.test", "BranchPass123"),
            ("inactive", "inactive@e2e.test", "InactivePass123"),
            ("noprofile", "noprofile@e2e.test", "NoProfilePass123"),
            ("reset", "reset@e2e.test", "OldPassword123"),
            ("session", "session@e2e.test", "SessionPass123"),
        ]:
            _, r = http("POST", f"{AUTH}/__control/seed", {"email": email, "password": pw})
            users[key] = {"id": r["id"], "email": email, "password": pw}
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(
                "insert into public.profiles (user_id, full_name, role) values (%s,'E2E Owner','owner')",
                (users["owner"]["id"],),
            )
            c.execute(
                "insert into public.profiles (user_id, full_name, role, branch_id) values (%s,'E2E Branch User','branch',%s)",
                (users["branch"]["id"], b1[0]),
            )
            c.execute(
                "insert into public.profiles (user_id, full_name, role, branch_id, is_active) values (%s,'E2E Inactive','branch',%s,false)",
                (users["inactive"]["id"], b1[0]),
            )
            for k in ("reset", "session"):
                c.execute(
                    "insert into public.profiles (user_id, full_name, role) values (%s,%s,'owner')",
                    (users[k]["id"], f"E2E {k.title()}"),
                )

        run_api_scenarios(users, dsn, b1, b2)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=CHROME, headless=True, args=["--no-sandbox"]
            )
            run_browser_scenarios(browser, users, dsn)
            browser.close()
        run_provisioning_scenarios(dsn, b2)
    finally:
        stop_all()
        time.sleep(0.5)
        admin.execute("alter role app_api nologin")
        admin.execute(f'drop database if exists "{dbname}" with (force)')
        admin.close()

    failed = [r for r in results if not r[1]]
    print(
        f"\n{len(results) - len(failed)}/{len(results)} scenarios passed (SIMULATED Auth server; see docs/authentication/AUTH_TEST_RESULTS.md)"
    )
    pathlib.Path("/tmp/e2e_results.json").write_text(json.dumps(results))
    return 1 if failed else 0


# ------------------------------------------------------------------------------------------------ API level
def run_api_scenarios(users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    @scenario("API: no token / garbage token -> 401 with WWW-Authenticate")
    def _() -> None:
        for headers in ({}, {"Authorization": "Bearer abc"}, {"Authorization": "Basic Zm9v"}):
            req = urllib.request.Request(f"{API}/api/v1/auth/me", headers=headers)
            try:
                urllib.request.urlopen(req)
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401 and e.headers["WWW-Authenticate"] == "Bearer"

    _()

    @scenario(
        "API: real sign-in token -> /auth/me and /auth/profile (owner, branch) under RLS as app_api"
    )
    def _() -> None:
        t = sign_in_token(users["owner"]["email"], users["owner"]["password"])
        s, me = http("GET", f"{API}/api/v1/auth/me", headers={"Authorization": f"Bearer {t}"})
        assert (
            s == 200
            and me["user_id"] == users["owner"]["id"]
            and "access_token" not in json.dumps(me)
        )
        s, p = http("GET", f"{API}/api/v1/auth/profile", headers={"Authorization": f"Bearer {t}"})
        assert s == 200 and p["role"] == "owner" and p["branch_id"] is None
        tb = sign_in_token(users["branch"]["email"], users["branch"]["password"])
        s, p = http("GET", f"{API}/api/v1/auth/profile", headers={"Authorization": f"Bearer {tb}"})
        assert s == 200 and p["role"] == "branch" and p["branch_name"] == b1[1]

    _()

    @scenario(
        "API: missing profile -> 403 profile_missing; inactive -> 403 account_inactive; /me still 200"
    )
    def _() -> None:
        t = sign_in_token(users["noprofile"]["email"], users["noprofile"]["password"])
        s, e = http("GET", f"{API}/api/v1/auth/profile", headers={"Authorization": f"Bearer {t}"})
        assert (s, e["error"]["code"]) == (403, "profile_missing")
        assert (
            http("GET", f"{API}/api/v1/auth/me", headers={"Authorization": f"Bearer {t}"})[0] == 200
        )
        t = sign_in_token(users["inactive"]["email"], users["inactive"]["password"])
        s, e = http("GET", f"{API}/api/v1/auth/profile", headers={"Authorization": f"Bearer {t}"})
        assert (s, e["error"]["code"]) == (403, "account_inactive")

    _()

    @scenario(
        "RBAC API: owner sees 10 branches; branch user only their own; other branch/other-user routes -> 403"
    )
    def _() -> None:
        to = sign_in_token(users["owner"]["email"], users["owner"]["password"])
        tb = sign_in_token(users["branch"]["email"], users["branch"]["password"])
        ho, hb = {"Authorization": f"Bearer {to}"}, {"Authorization": f"Bearer {tb}"}
        s, rows = http("GET", f"{API}/api/v1/branches", headers=ho)
        assert s == 200 and len(rows) == 10
        s, rows = http("GET", f"{API}/api/v1/branches", headers=hb)
        assert s == 200 and [r["id"] for r in rows] == [str(b1[0])]
        s, e = http("GET", f"{API}/api/v1/branches/{b2[0]}", headers=hb)
        assert (s, e["error"]["code"]) == (403, "branch_access_denied")
        s, e = http("GET", f"{API}/api/v1/branches?branch_id={b2[0]}", headers=hb)
        assert (s, e["error"]["code"]) == (403, "branch_access_denied")
        s, e = http("GET", f"{API}/api/v1/users", headers=hb)
        assert (s, e["error"]["code"]) == (403, "permission_denied")
        s, rows = http("GET", f"{API}/api/v1/users", headers=ho)
        assert s == 200 and len(rows) >= 4
        s, p = http("GET", f"{API}/api/v1/auth/profile", headers=hb)
        assert (
            "suppliers" not in p["permissions"]
            and p["permissions"]["daily_reports"]["scope"] == "own_branch"
        )

    _()

    @scenario("RBAC API: denied attempts are in the audit log (no tokens), allowed ones are not")
    def _() -> None:
        with psycopg.connect(dsn) as c:
            rows = c.execute(
                "select new_values from public.audit_log where action='ACCESS_DENIED' and actor_user_id=%s",
                (users["branch"]["id"],),
            ).fetchall()
            owner_rows = c.execute(
                "select count(*) from public.audit_log where action='ACCESS_DENIED' and actor_user_id=%s",
                (users["owner"]["id"],),
            ).fetchone()[0]
        mods = {r[0]["module"] for r in rows}
        assert {"branch_management", "user_management"} <= mods, mods
        assert "bearer" not in json.dumps(rows).lower() and owner_rows == 0

    _()

    @scenario("API: token from an unrelated signing key is rejected (wrong issuer/key)")
    def _() -> None:
        import jwt
        from cryptography.hazmat.primitives.asymmetric import ec

        k = ec.generate_private_key(ec.SECP256R1())
        now = int(time.time())
        forged = jwt.encode(
            {
                "iss": f"{AUTH}/auth/v1",
                "aud": "authenticated",
                "sub": users["owner"]["id"],
                "role": "authenticated",
                "exp": now + 600,
            },
            k,
            algorithm="ES256",
            headers={"kid": "forged"},
        )
        s, e = http("GET", f"{API}/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert (s, e["error"]["code"]) == (401, "invalid_token")

    _()


# ------------------------------------------------------------------------------------------------ browser level
def run_browser_scenarios(browser: Browser, users: dict, dsn: str) -> None:
    def new_ctx() -> tuple[BrowserContext, Page]:
        ctx = browser.new_context()
        ctx.add_init_script("""
          new MutationObserver(() => {
            if ([...document.querySelectorAll('h1')].some(h => h.textContent === 'Sign in')) sessionStorage.setItem('__sawLogin', '1')
          }).observe(document, {childList: true, subtree: true})
        """)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        return ctx, page

    @scenario("UI: unauthenticated visit to a protected URL redirects to /login")
    def _() -> None:
        ctx, page = new_ctx()
        page.goto(f"{WEB}/system-status")
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        assert page.url.endswith("/login")
        ctx.close()

    _()

    @scenario("UI: wrong password shows a generic error and stays on login")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], "totally-wrong")
        expect(page.get_by_role("alert")).to_contain_text("Incorrect email or password")
        login_ui(page, "nobody@e2e.test", "totally-wrong")
        expect(page.get_by_role("alert")).to_contain_text("Incorrect email or password")
        ctx.close()

    _()

    @scenario("UI: owner login -> protected page, API called with bearer token, profile shown")
    def _() -> None:
        ctx, page = new_ctx()
        seen: list[tuple[str, str | None, int | None]] = []
        page.on(
            "response",
            lambda r: (
                seen.append((r.url, r.request.headers.get("authorization"), r.status))
                if "/auth/profile" in r.url
                else None
            ),
        )
        login_ui(page, users["owner"]["email"], users["owner"]["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        expect(page.get_by_text("E2E Owner").first).to_be_visible()
        assert any(a and a.startswith("Bearer ") and st == 200 for _u, a, st in seen), seen
        ctx.close()

    _()

    @scenario("UI: session persists across reload and new tab with NO login flicker")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], users["owner"]["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        page.evaluate("sessionStorage.removeItem('__sawLogin')")
        for _i in range(3):
            page.reload()
            expect(page.get_by_text("Welcome")).to_be_visible()
        assert page.evaluate("sessionStorage.getItem('__sawLogin')") is None, (
            "login page flashed during restoration"
        )
        other = ctx.new_page()
        other.goto(f"{WEB}/")
        expect(other.get_by_text("Welcome")).to_be_visible()
        assert "alsafa-auth" in " ".join(page.evaluate("Object.keys(localStorage)"))
        ctx.close()

    _()

    @scenario(
        "UI: 'Keep me signed in' unchecked -> session only in sessionStorage (gone in a new context)"
    )
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], users["owner"]["password"], remember=False)
        expect(page.get_by_text("Welcome")).to_be_visible()
        keys_local = page.evaluate("Object.keys(localStorage).filter(k => k === 'alsafa-auth')")
        keys_sess = page.evaluate("Object.keys(sessionStorage).filter(k => k === 'alsafa-auth')")
        assert keys_local == [] and keys_sess == ["alsafa-auth"], (keys_local, keys_sess)
        ctx2, page2 = new_ctx()
        page2.goto(f"{WEB}/")
        expect(page2.get_by_role("heading", name="Sign in")).to_be_visible()
        ctx.close()
        ctx2.close()

    _()

    @scenario("UI: branch user sees role and branch")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["branch"]["email"], users["branch"]["password"])
        expect(page.get_by_text("E2E Branch User").first).to_be_visible()
        expect(page.get_by_text("branch", exact=True).first).to_be_visible()
        ctx.close()

    _()

    @scenario("UI: inactive account and account without profile are blocked")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["inactive"]["email"], users["inactive"]["password"])
        expect(page.get_by_text("Account inactive")).to_be_visible()
        expect(page.get_by_text("Welcome")).to_have_count(0)
        page.get_by_role("button", name="Sign out").click()
        login_ui(page, users["noprofile"]["email"], users["noprofile"]["password"])
        expect(page.get_by_text("Account not set up")).to_be_visible()
        ctx.close()

    _()

    @scenario("UI: logout clears the session; reload and protected URLs stay on /login")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], users["owner"]["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        page.get_by_role("button", name="Sign out").click()
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        assert (
            page.evaluate(
                "Object.keys(localStorage).concat(Object.keys(sessionStorage)).filter(k => k === 'alsafa-auth').length"
            )
            == 0
        )
        page.reload()
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        page.goto(f"{WEB}/system-status")
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        expect(page.get_by_text(re.compile("session has ended"))).to_have_count(0)
        ctx.close()

    _()

    @scenario(
        "UI: password reset end to end (request -> email link -> new password -> old password rejected)"
    )
    def _() -> None:
        u = users["reset"]
        ctx, page = new_ctx()
        page.goto(f"{WEB}/forgot-password")
        page.get_by_label("Email").fill(u["email"])
        page.get_by_role("button", name="Send reset link").click()
        expect(page.get_by_role("status")).to_contain_text("If an account exists")
        _, outbox = http("GET", f"{AUTH}/__control/outbox")
        mail = [m for m in outbox if m["to"] == u["email"]][-1]
        assert mail["link"].endswith("redirect_to=" + WEB + "/reset-password"), mail["link"]
        page.goto(mail["link"])
        expect(page.get_by_role("heading", name="Choose a new password")).to_be_visible()
        page.get_by_label("New password", exact=True).fill("short1")
        page.get_by_label("Confirm new password").fill("short1")
        page.get_by_role("button", name="Update password").click()
        expect(page.get_by_text("Use at least 10 characters")).to_be_visible()
        page.get_by_label("New password", exact=True).fill("BrandNewPass456")
        page.get_by_label("Confirm new password").fill("Different456")
        page.get_by_role("button", name="Update password").click()
        expect(page.get_by_text("Passwords do not match")).to_be_visible()
        page.get_by_label("Confirm new password").fill("BrandNewPass456")
        page.get_by_role("button", name="Update password").click()
        expect(page.get_by_text("Your password has been updated")).to_be_visible()
        login_ui(page, u["email"], u["password"])  # old password
        expect(page.get_by_role("alert")).to_contain_text("Incorrect email or password")
        login_ui(page, u["email"], "BrandNewPass456")
        expect(page.get_by_text("Welcome")).to_be_visible()
        # the one-time link cannot be reused
        page.get_by_role("button", name="Sign out").click()
        page.goto(mail["link"])
        expect(page.get_by_text("Reset link not valid")).to_be_visible()
        ctx.close()

    _()

    @scenario(
        "UI: reset link opened in a different browser (no PKCE verifier) is rejected; forgot-password never reveals accounts"
    )
    def _() -> None:
        ctx, page = new_ctx()
        page.goto(f"{WEB}/forgot-password")
        page.get_by_label("Email").fill(users["owner"]["email"])
        page.get_by_role("button", name="Send reset link").click()
        expect(page.get_by_role("status")).to_be_visible()
        link = [
            m
            for m in http("GET", f"{AUTH}/__control/outbox")[1]
            if m["to"] == users["owner"]["email"]
        ][-1]["link"]
        ctx2, page2 = new_ctx()
        page2.goto(link)
        expect(page2.get_by_text("Reset link not valid")).to_be_visible()
        a = new_ctx()
        a[1].goto(f"{WEB}/forgot-password")
        a[1].get_by_label("Email").fill("ghost@e2e.test")
        a[1].get_by_role("button", name="Send reset link").click()
        expect(a[1].get_by_role("status")).to_contain_text("If an account exists")
        ctx.close()
        ctx2.close()
        a[0].close()

    _()

    @scenario(
        "RBAC UI: branch user sees only permitted navigation and is blocked from owner pages by URL"
    )
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["branch"]["email"], users["branch"]["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        nav = page.get_by_role("navigation", name="Main")
        expect(nav.get_by_role("link")).to_have_count(1)
        expect(nav.get_by_role("link", name="Dashboard")).to_be_visible()
        page.goto(f"{WEB}/system-status")
        expect(page.get_by_text("Access denied")).to_be_visible()
        expect(page.get_by_text("Backend API")).to_have_count(0)
        page.reload()
        expect(page.get_by_text("Access denied")).to_be_visible()
        ctx.close()

    _()

    @scenario("RBAC UI: owner sees administrative navigation and can open owner pages by URL")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], users["owner"]["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        expect(
            page.get_by_role("navigation", name="Main").get_by_role("link", name="System status")
        ).to_be_visible()
        page.goto(f"{WEB}/system-status")
        expect(page.get_by_text("Application foundation")).to_be_visible()
        ctx.close()

    _()

    @scenario(
        "UI: deactivating a signed-in user takes effect on the next load (token alone is not enough)"
    )
    def _() -> None:
        u = users["session"]
        ctx, page = new_ctx()
        login_ui(page, u["email"], u["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("update public.profiles set is_active=false where user_id=%s", (u["id"],))
        page.reload()
        expect(page.get_by_text("Account inactive")).to_be_visible()
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("update public.profiles set is_active=true where user_id=%s", (u["id"],))
        ctx.close()

    _()

    @scenario(
        "UI: signing key rotation -> old session gets 401 -> signed out with notice; new sign-in works (JWKS refresh)"
    )
    def _() -> None:
        u = users["session"]
        ctx, page = new_ctx()
        login_ui(page, u["email"], u["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        http("POST", f"{AUTH}/__control/rotate_keys", {})
        time.sleep(
            2.5
        )  # exceed the E2E JWKS cache TTL (2s): the retired key is dropped on the next refresh
        page.reload()
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        expect(page.get_by_text("Your session has ended")).to_be_visible()
        login_ui(page, u["email"], u["password"])
        expect(page.get_by_text("Welcome")).to_be_visible()
        ctx.close()

    _()


# ------------------------------------------------------------------------------------------------ provisioning
def run_provisioning_scenarios(dsn: str, branch: tuple) -> None:
    env = {
        **os.environ,
        "SUPABASE_URL": AUTH,
        "SUPABASE_SERVICE_ROLE_KEY": SERVICE_KEY,
        "ADMIN_DATABASE_URL": dsn,
        "PASSWORD_RESET_REDIRECT_URL": f"{WEB}/reset-password",
    }

    def prov(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [PY, "backend/scripts/provision_account.py", *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def profile(email: str) -> tuple | None:
        with psycopg.connect(dsn) as c:
            return c.execute(
                "select p.role, p.is_active, b.name from public.profiles p join auth.users u on u.id=p.user_id "
                "left join public.branches b on b.id=p.branch_id where u.email=%s",
                (email,),
            ).fetchone()

    @scenario(
        "PROVISION: create branch user -> Auth user + profile + password-set email; no password printed"
    )
    def _() -> None:
        r = prov(
            "create",
            "--email",
            "new.branch@e2e.test",
            "--full-name",
            "New Branch",
            "--role",
            "branch",
            "--branch",
            branch[1].lower(),
        )
        assert r.returncode == 0, r.stderr
        assert profile("new.branch@e2e.test") == ("branch", True, branch[1])
        assert any(
            m["to"] == "new.branch@e2e.test" for m in http("GET", f"{AUTH}/__control/outbox")[1]
        )
        assert SERVICE_KEY not in r.stdout + r.stderr

    _()

    @scenario("PROVISION: invalid branch -> error, and the Auth user is rolled back (no orphan)")
    def _() -> None:
        before = len(
            http(
                "GET",
                f"{AUTH}/auth/v1/admin/users",
                headers={"Authorization": f"Bearer {SERVICE_KEY}"},
            )[1]["users"]
        )
        r = prov(
            "create",
            "--email",
            "orphan@e2e.test",
            "--full-name",
            "X",
            "--role",
            "branch",
            "--branch",
            "NOT A BRANCH",
        )
        assert r.returncode == 1 and "unknown branch" in r.stderr
        after = len(
            http(
                "GET",
                f"{AUTH}/auth/v1/admin/users",
                headers={"Authorization": f"Bearer {SERVICE_KEY}"},
            )[1]["users"]
        )
        assert before == after and profile("orphan@e2e.test") is None

    _()

    @scenario(
        "PROVISION: rule violations rejected (owner with branch, branch without branch, duplicate profile)"
    )
    def _() -> None:
        assert (
            prov(
                "create",
                "--email",
                "o1@e2e.test",
                "--full-name",
                "O",
                "--role",
                "owner",
                "--branch",
                branch[1],
            ).returncode
            == 1
        )
        assert (
            prov(
                "create", "--email", "b1@e2e.test", "--full-name", "B", "--role", "branch"
            ).returncode
            == 1
        )
        r = prov(
            "create", "--email", "new.owner@e2e.test", "--full-name", "New Owner", "--role", "owner"
        )
        assert r.returncode == 0 and profile("new.owner@e2e.test") == ("owner", True, None)

    _()

    @scenario("PROVISION: deactivate -> profile inactive + Auth sign-in blocked; activate restores")
    def _() -> None:
        _s, body = http(
            "POST",
            f"{AUTH}/__control/seed",
            {"email": "toggle@e2e.test", "password": "TogglePass123"},
        )
        r = prov("adopt", "--user-id", body["id"], "--full-name", "Toggle", "--role", "owner")
        assert r.returncode == 0, r.stderr
        assert prov("deactivate", "--email", "toggle@e2e.test").returncode == 0
        assert profile("toggle@e2e.test")[1] is False
        s, e = http(
            "POST",
            f"{AUTH}/auth/v1/token?grant_type=password",
            {"email": "toggle@e2e.test", "password": "TogglePass123"},
        )
        assert s == 400 and e["error_code"] == "user_banned"
        assert prov("activate", "--user-id", body["id"]).returncode == 0
        assert profile("toggle@e2e.test")[1] is True
        assert (
            http(
                "POST",
                f"{AUTH}/auth/v1/token?grant_type=password",
                {"email": "toggle@e2e.test", "password": "TogglePass123"},
            )[0]
            == 200
        )

    _()

    @scenario("PROVISION: refuses to run without service key / admin DB configuration")
    def _() -> None:
        bad = {k: v for k, v in env.items() if k != "SUPABASE_SERVICE_ROLE_KEY"}
        r = subprocess.run(
            [PY, "backend/scripts/provision_account.py", "deactivate", "--email", "x@y.test"],
            cwd=ROOT,
            env=bad,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 1 and "SUPABASE_SERVICE_ROLE_KEY" in r.stderr

    _()


if __name__ == "__main__":
    sys.exit(main())
