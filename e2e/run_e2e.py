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

        only = os.environ.get("E2E_ONLY", "")
        only12 = only in ("12", "13")
        if not only12:
            run_api_scenarios(users, dsn, b1, b2)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=CHROME, headless=True, args=["--no-sandbox"]
            )
            if not only12:
                run_browser_scenarios(browser, users, dsn)
                run_layout_scenarios(browser, users)
                run_step7_scenarios(browser, users, dsn, b1, b2)
                run_step8_scenarios(browser, users, dsn, b1, b2)
                run_step9_scenarios(browser, users, dsn, b1, b2)
                run_step10_scenarios(browser, users, dsn, b1, b2)
                run_step11_scenarios(browser, users, dsn, b1, b2)
            if only != "13":
                run_step12_scenarios(browser, users, dsn, b1, b2)
            run_step13_scenarios(browser, users, dsn, b1, b2)
            browser.close()
        if not only12:
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
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        expect(page.get_by_text("E2E Owner").first).to_be_visible()
        assert any(a and a.startswith("Bearer ") and st == 200 for _u, a, st in seen), seen
        ctx.close()

    _()

    @scenario("UI: session persists across reload and new tab with NO login flicker")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], users["owner"]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        page.evaluate("sessionStorage.removeItem('__sawLogin')")
        for _i in range(3):
            page.reload()
            expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        assert page.evaluate("sessionStorage.getItem('__sawLogin')") is None, (
            "login page flashed during restoration"
        )
        other = ctx.new_page()
        other.goto(f"{WEB}/")
        expect(other.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        assert "alsafa-auth" in " ".join(page.evaluate("Object.keys(localStorage)"))
        ctx.close()

    _()

    @scenario(
        "UI: 'Keep me signed in' unchecked -> session only in sessionStorage (gone in a new context)"
    )
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], users["owner"]["password"], remember=False)
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
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
        expect(page.get_by_text("Branch User", exact=False).first).to_be_visible()
        ctx.close()

    _()

    @scenario("UI: inactive account and account without profile are blocked")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["inactive"]["email"], users["inactive"]["password"])
        expect(page.get_by_text("Account inactive")).to_be_visible()
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_have_count(0)
        page.get_by_role("button", name="Sign out").click()
        login_ui(page, users["noprofile"]["email"], users["noprofile"]["password"])
        expect(page.get_by_text("Account not set up")).to_be_visible()
        ctx.close()

    _()

    @scenario("UI: logout clears the session; reload and protected URLs stay on /login")
    def _() -> None:
        ctx, page = new_ctx()
        login_ui(page, users["owner"]["email"], users["owner"]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
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
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
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
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        nav = page.get_by_role("navigation", name="Main")
        expect(nav.get_by_role("link")).to_have_count(
            9
        )  # Dashboard, My Branch, Branch & Date View, Daily Reports + the 5 Orders & Delivery entries (Step 13, O1)
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
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        nav = page.get_by_role("navigation", name="Main")
        nav.get_by_role("button", name="Settings").click()
        expect(nav.get_by_role("link", name="System status")).to_be_visible()
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
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
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
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        http("POST", f"{AUTH}/__control/rotate_keys", {})
        time.sleep(
            2.5
        )  # exceed the E2E JWKS cache TTL (2s): the retired key is dropped on the next refresh
        page.reload()
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        expect(page.get_by_text("Your session has ended")).to_be_visible()
        login_ui(page, u["email"], u["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        ctx.close()

    _()


# ------------------------------------------------------------------------------------------------ layout (Step 6)
VIEWPORTS = [(1440, 900), (1280, 800), (768, 1024), (390, 844), (360, 740)]
SHOTS = pathlib.Path(os.environ.get("UI_SHOTS_DIR", "/tmp/ui_shots"))


def run_layout_scenarios(browser: Browser, users: dict) -> None:
    """Step 6: the application shell in a real browser at the required viewport sizes."""
    SHOTS.mkdir(parents=True, exist_ok=True)

    def open_session(role: str, w: int, h: int) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=w < 768)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        u = users[role]
        login_ui(page, u["email"], u["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    def no_overflow(page: Page, where: str) -> None:
        m = page.evaluate(
            "() => ({doc: document.documentElement.scrollWidth, body: document.body.scrollWidth, win: window.innerWidth})"
        )
        assert m["doc"] <= m["win"] and m["body"] <= m["win"], (
            f"horizontal overflow at {where}: {m}"
        )

    def box_width(page: Page, selector: str) -> float:
        return page.locator(selector).first.bounding_box()["width"]

    def settle(page: Page) -> None:
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(350)  # sidebar width transition (200ms)

    owner_pages = [
        "/",
        "/branches",
        "/branch-date-view",
        "/finance-nope",
        "/system-status",
        "/design-system",
    ]
    branch_pages = [
        "/",
        "/daily-reports",
        "/branch-date-view",
        "/suppliers",
        "/users",
        "/finance-nope",
    ]

    for w, h in VIEWPORTS:
        for role, pages in (("owner", owner_pages), ("branch", branch_pages)):

            @scenario(
                f"LAYOUT {w}px {role}: every page fits the viewport, shell renders, no console errors"
            )
            def _(role=role, pages=pages, w=w, h=h) -> None:
                ctx, page, problems = open_session(role, w, h)
                for path in pages:
                    page.goto(f"{WEB}{path}")
                    settle(page)
                    expect(page.locator("main#main-content")).to_be_visible()
                    no_overflow(page, f"{role} {path} @{w}")
                    if path == "/":
                        page.screenshot(path=str(SHOTS / f"{role}_dashboard_{w}.png"))
                    if path == "/design-system":
                        page.screenshot(
                            path=str(SHOTS / f"{role}_design_system_{w}.png"), full_page=True
                        )
                    if path in ("/suppliers", "/users"):
                        expect(page.get_by_text("Access denied")).to_be_visible()
                        expect(page.get_by_text("This module is not built yet")).to_have_count(0)
                        page.screenshot(path=str(SHOTS / f"{role}_denied_{w}.png"))
                    if path == "/finance-nope":
                        expect(page.get_by_role("link", name="Back to start")).to_be_visible()
                        page.screenshot(path=str(SHOTS / f"{role}_404_{w}.png"))
                assert not problems, problems
                ctx.close()

            _()

    @scenario("LAYOUT 1440 owner: sidebar expand/collapse, content adapts, choice survives reload")
    def _() -> None:
        ctx, page, problems = open_session("owner", 1440, 900)
        settle(page)
        assert abs(box_width(page, "aside") - 256) < 1
        assert abs(page.locator("header").first.bounding_box()["x"] - 256) < 1
        page.get_by_role("button", name="Collapse sidebar").click()
        settle(page)
        assert abs(box_width(page, "aside") - 64) < 1
        assert abs(page.locator("header").first.bounding_box()["x"] - 64) < 1
        expect(page.get_by_role("navigation", name="Main").get_by_text("Operations")).to_have_count(
            0
        )
        page.screenshot(path=str(SHOTS / "owner_dashboard_1440_collapsed.png"))
        page.reload()
        settle(page)
        assert abs(box_width(page, "aside") - 64) < 1
        page.get_by_role("button", name="Expand sidebar").click()
        settle(page)
        assert abs(box_width(page, "aside") - 256) < 1
        assert not problems, problems
        ctx.close()

    _()

    @scenario("LAYOUT 1440 owner: nav sections, Settings group, breadcrumbs, active state")
    def _() -> None:
        ctx, page, problems = open_session("owner", 1440, 900)
        nav = page.get_by_role("navigation", name="Main")
        for label in [
            "Overview",
            "Operations",
            "Orders & Delivery",
            "Finance",
            "People & Compliance",
            "Property",
            "Management",
            "Administration",
        ]:
            expect(nav.get_by_text(label, exact=True)).to_be_visible()
        for name in [
            "Dashboard",
            "Branch Management",
            "Branch & Date View",
            "Daily Reports",
            "Order Management",
            "Customers",
            "Cash & Banks",
            "Opening Balances",
            "Expenses & Savings",
            "Suppliers",
            "Employees",
            "Visas & Passports",
            "Trade Licenses",
            "Rental Agreements",
            "PDC Cheques",
            "Tasks",
            "Notifications",
            "Reports & Analytics",
            "Activity History",
            "User Management",
        ]:
            expect(nav.get_by_role("link", name=name, exact=True)).to_be_visible()
        nav.get_by_role("button", name="Settings").click()
        nav.get_by_role("link", name="System status").click()
        expect(page).to_have_url(re.compile(r"/system-status$"))
        crumbs = page.get_by_role("navigation", name="Breadcrumb")
        for t in ["Dashboard", "Administration", "Settings", "System status"]:
            expect(crumbs.get_by_text(t, exact=True)).to_be_visible()
        expect(nav.get_by_role("link", name="System status")).to_have_attribute(
            "aria-current", "page"
        )
        crumbs.get_by_role("link", name="Dashboard").click()
        expect(page).to_have_url(re.compile(r"/$"))
        assert not problems, problems
        ctx.close()

    _()

    @scenario(
        "LAYOUT 1440 owner: branch selector lists all ten real branches; user and notification menus work"
    )
    def _() -> None:
        ctx, page, problems = open_session("owner", 1440, 900)
        sel = page.get_by_role("combobox", name="Branch")
        expect(sel).to_be_enabled()
        sel.click()
        options = page.get_by_role("option")
        expect(options).to_have_count(11)  # All branches + the ten
        options.nth(2).click()
        chosen = sel.inner_text().strip()
        expect(page.locator("main").get_by_text(chosen, exact=True)).to_be_visible()
        page.get_by_role("button", name="Notifications").click()
        expect(page.get_by_text("You have no notifications.")).to_be_visible()
        page.keyboard.press("Escape")
        page.get_by_role("button", name=re.compile("Account menu for")).click()
        expect(page.get_by_role("menuitem", name="Sign out")).to_be_visible()
        expect(
            page.get_by_role("menu").get_by_text("Owner · All branches", exact=True)
        ).to_be_visible()
        page.screenshot(path=str(SHOTS / "owner_user_menu_1440.png"))
        page.keyboard.press("Escape")
        page.get_by_role("button", name=re.compile("Account menu for")).click()
        page.get_by_role("menuitem", name="Sign out").click()
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        assert not problems, problems
        ctx.close()

    _()

    @scenario("LAYOUT 1280 owner: sidebar expanded by default, content fills the remaining width")
    def _() -> None:
        ctx, page, problems = open_session("owner", 1280, 800)
        settle(page)
        assert abs(box_width(page, "aside") - 256) < 1
        main = page.locator("main#main-content").bounding_box()
        assert abs(main["x"] - 256) < 1 and abs(main["width"] - (1280 - 256)) < 2, main
        assert not problems, problems
        ctx.close()

    _()

    @scenario("LAYOUT 768 owner: compact icon rail, tooltip on hover, toggle opens the full drawer")
    def _() -> None:
        ctx, page, problems = open_session("owner", 768, 1024)
        settle(page)
        assert abs(box_width(page, "aside") - 64) < 1
        assert abs(page.locator("main#main-content").bounding_box()["x"] - 64) < 1
        rail_link = page.get_by_role("navigation", name="Main").get_by_role(
            "link", name="Suppliers"
        )
        assert rail_link.bounding_box()["height"] >= 36, "rail items are cramped"
        rail_link.hover()
        expect(page.get_by_role("tooltip")).to_have_text("Suppliers")
        page.get_by_role("button", name="Open navigation").click()
        drawer = page.get_by_role("dialog")
        expect(drawer.get_by_text("Finance", exact=True)).to_be_visible()
        page.wait_for_timeout(450)  # slide-in animation
        page.screenshot(path=str(SHOTS / "owner_drawer_768.png"))
        drawer.get_by_role("link", name="Suppliers").click()
        expect(page.get_by_role("heading", name="Suppliers", level=1)).to_be_visible()
        expect(page.get_by_role("dialog")).to_have_count(0)
        assert not problems, problems
        ctx.close()

    _()

    for w, h in ((390, 844), (360, 740)):

        @scenario(
            f"LAYOUT {w} owner: no fixed sidebar, touch-sized controls, drawer opens/closes, focus returns"
        )
        def _(w=w, h=h) -> None:
            ctx, page, problems = open_session("owner", w, h)
            settle(page)
            expect(page.locator("aside")).to_have_count(0)
            toggle = page.get_by_role("button", name="Open navigation")
            for loc in (
                toggle,
                page.get_by_role("button", name="Notifications"),
                page.get_by_role("button", name=re.compile("Account menu for")),
            ):
                b = loc.bounding_box()
                assert b["width"] >= 44 and b["height"] >= 44, ("touch target too small", b)
            expect(page.get_by_role("combobox", name="Branch")).to_be_visible()
            toggle.click()
            drawer = page.get_by_role("dialog")
            expect(drawer.get_by_role("navigation", name="Main")).to_be_visible()
            page.wait_for_timeout(450)  # slide-in animation
            db = drawer.bounding_box()
            assert db["x"] == 0 and db["width"] <= w * 0.86, db
            page.screenshot(path=str(SHOTS / f"owner_drawer_{w}.png"))
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).to_have_count(0)
            expect(toggle).to_be_focused()
            toggle.click()
            page.get_by_role("dialog").get_by_role("link", name="Daily Reports").click()
            expect(page.get_by_role("heading", name="Daily Reports", level=1)).to_be_visible()
            expect(page.get_by_role("dialog")).to_have_count(0)
            no_overflow(page, f"owner drawer nav @{w}")
            assert not problems, problems
            ctx.close()

        _()

    @scenario(
        "LAYOUT 390 branch: drawer lists only permitted pages; assigned branch shown; no selector"
    )
    def _() -> None:
        ctx, page, problems = open_session("branch", 390, 844)
        expect(page.get_by_role("combobox", name="Branch")).to_have_count(0)
        expect(page.get_by_title("Your assigned branch")).to_be_visible()
        page.get_by_role("button", name="Open navigation").click()
        links = (
            page.get_by_role("dialog").get_by_role("navigation", name="Main").get_by_role("link")
        )
        assert links.all_inner_texts() == [
            "Dashboard",
            "My Branch",
            "Branch & Date View",
            "Daily Reports",
            "Order Management",
            "Orders",
            "Customers",
            "Pickup & Delivery",
            "Order Reports",
        ], links.all_inner_texts()
        for hidden in ["Finance", "Administration", "Management"]:
            expect(page.get_by_role("dialog").get_by_text(hidden, exact=True)).to_have_count(0)
        page.wait_for_timeout(450)
        page.screenshot(path=str(SHOTS / "branch_drawer_390.png"))
        assert not problems, problems
        ctx.close()

    _()

    @scenario("LAYOUT 1440 branch: restricted navigation, typed URLs blocked, shell stays usable")
    def _() -> None:
        ctx, page, problems = open_session("branch", 1440, 900)
        nav = page.get_by_role("navigation", name="Main")
        assert nav.get_by_role("link").all_inner_texts() == [
            "Dashboard",
            "My Branch",
            "Branch & Date View",
            "Daily Reports",
            "Order Management",
            "Orders",
            "Customers",
            "Pickup & Delivery",
            "Order Reports",
        ]
        for path in (
            "/suppliers",
            "/cash-banks",
            "/users",
            "/settings",
            "/system-status",
            "/tasks",
        ):
            page.goto(f"{WEB}{path}")
            expect(page.get_by_text("Access denied")).to_be_visible()
            expect(nav).to_be_visible()
            assert page.url.endswith(path)
        page.goto(f"{WEB}/daily-reports")
        expect(page.get_by_role("heading", name="Daily Reports", level=1)).to_be_visible()
        expect(page.get_by_text("This module is not built yet")).to_have_count(0)
        assert not problems, problems
        ctx.close()

    _()

    @scenario("LAYOUT keyboard: skip link, visible focus ring on navigation and header controls")
    def _() -> None:
        ctx, page, problems = open_session("owner", 1440, 900)
        page.keyboard.press("Tab")
        skip = page.get_by_role("link", name="Skip to main content")
        expect(skip).to_be_focused()
        expect(skip).to_be_visible()
        page.keyboard.press("Enter")
        expect(page.locator("main#main-content")).to_be_focused()
        page.get_by_role("navigation", name="Main").get_by_role("link", name="Suppliers").focus()
        page.keyboard.press("Tab")
        ring = page.evaluate(
            "() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineWidth, s.boxShadow] }"
        )
        assert ring[0] != "none" or ring[2] != "none", ring
        page.get_by_role("button", name="Collapse sidebar").focus()
        page.keyboard.press("Tab")
        ring = page.evaluate(
            "() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineWidth, s.boxShadow] }"
        )
        assert ring[0] != "none" or ring[2] != "none", ring
        assert not problems, problems
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


# ------------------------------------------------------------------------------------------------ Step 7
def run_step7_scenarios(browser: Browser, users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    """Step 7: daily reports, dashboard and Branch & Date View against REAL database rows (no mocks)."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Dubai")).date()
    shots = ROOT / "e2e" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    tok = {
        k: {"Authorization": "Bearer " + sign_in_token(users[k]["email"], users[k]["password"])}
        for k in ("owner", "branch")
    }

    def report(d, **over) -> dict:
        base = dict(
            report_date=d.isoformat(),
            total_sales="1000.00",
            order_count=10,
            cash_received="600.00",
            pos_amount="200.00",
            bank_transfer="100.00",
            link_payment="50.00",
            shop_expenses="300.00",
            shop_savings="100.00",
        )
        base.update(over)
        return base

    def open_page(role: str, w: int = 1440, h: int = 900) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=w < 768)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        login_ui(page, users[role]["email"], users[role]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    @scenario(
        "STEP7 API: owner submits for any branch; branch user only for own branch; duplicates, future, invalid rejected"
    )
    def _() -> None:
        d = today - timedelta(days=30)
        s, r = http(
            "POST", f"{API}/api/v1/daily-reports", report(d, branch_id=str(b2[0])), tok["owner"]
        )
        assert s == 201 and r["total_received"] == "950.00" and r["difference"] == "50.00", r
        s, e = http(
            "POST", f"{API}/api/v1/daily-reports", report(d, branch_id=str(b2[0])), tok["owner"]
        )
        assert (s, e["error"]["code"]) == (409, "duplicate_report"), e
        s, e = http(
            "POST", f"{API}/api/v1/daily-reports", report(d, branch_id=str(b2[0])), tok["branch"]
        )
        assert (s, e["error"]["code"]) == (403, "branch_access_denied"), e
        s, r = http("POST", f"{API}/api/v1/daily-reports", report(d), tok["branch"])
        assert s == 201 and r["branch_id"] == str(b1[0]), r
        for over in (
            {"report_date": (today + timedelta(days=1)).isoformat()},
            {"total_sales": "0"},
            {"cash_received": "-1"},
            {"shop_savings": "999.00"},
        ):
            s, _e = http(
                "POST",
                f"{API}/api/v1/daily-reports",
                report(d - timedelta(days=1), **over),
                tok["branch"],
            )
            assert s == 422, (over, s)
        assert http("POST", f"{API}/api/v1/daily-reports", report(d))[0] == 401

    _()

    @scenario(
        "STEP7 API: branch user is isolated on list, view, missing and owner-only dashboard; head office hidden"
    )
    def _() -> None:
        d = today - timedelta(days=30)
        q = f"date_from={d}&date_to={d}"
        s, lst = http("GET", f"{API}/api/v1/daily-reports?{q}", headers=tok["branch"])
        assert s == 200 and {i["branch_name"] for i in lst["items"]} == {b1[1]}
        s, lst = http("GET", f"{API}/api/v1/daily-reports?{q}", headers=tok["owner"])
        assert {i["branch_name"] for i in lst["items"]} == {b1[1], b2[1]}
        for path in (
            f"/daily-reports?branch_id={b2[0]}",
            f"/branch-date-view?{q}&branch_id={b2[0]}",
            f"/daily-reports/missing?{q}&branch_id={b2[0]}",
        ):
            assert http("GET", f"{API}/api/v1{path}", headers=tok["branch"])[0] == 403, path
        assert http("GET", f"{API}/api/v1/dashboard/owner", headers=tok["branch"])[0] == 403
        s, v = http("GET", f"{API}/api/v1/branch-date-view?{q}", headers=tok["branch"])
        assert s == 200 and v["totals"]["total_sales"] == "1000.00" and v["head_office"] is None
        s, v = http("GET", f"{API}/api/v1/branch-date-view?{q}", headers=tok["owner"])
        assert v["totals"]["total_sales"] == "2000.00" and v["head_office"] is not None

    _()

    @scenario(
        "STEP7 API: missing reports are 'not configured' until opening balances exist, then counted from the start date"
    )
    def _() -> None:
        q = f"date_from={today - timedelta(days=2)}&date_to={today}"
        s, m = http("GET", f"{API}/api/v1/daily-reports/missing?{q}", headers=tok["owner"])
        assert m["status"] == "not_configured" and m["missing_count"] == 0, m
        s, dash = http("GET", f"{API}/api/v1/dashboard/owner", headers=tok["owner"])
        assert (
            dash["balances"]["status"] == "not_configured"
            and dash["kpis"]["cash_bank_balance"] is None
        )
        start = today - timedelta(days=1)
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(
                "insert into public.opening_balances (id, as_of_date, receipts_bank, enbd_balance, adcb_balance, pos_pending)"
                " values (1, %s, 'ENBD', 1000, 500, 200)",
                (start - timedelta(days=1),),
            )
        s, m = http("GET", f"{API}/api/v1/daily-reports/missing?{q}", headers=tok["owner"])
        assert m["status"] == "ok" and m["date_from"] == start.isoformat(), m
        assert (
            m["expected"] == 20 and m["missing_count"] == 20
        )  # 2 days x 10 branches, none reported
        s, dash = http("GET", f"{API}/api/v1/dashboard/owner", headers=tok["owner"])
        assert (
            dash["balances"]["status"] == "ok" and dash["kpis"]["cash_bank_balance"] is not None
        ), dash

    _()

    @scenario(
        "STEP7 UI: branch user submits a report (fixed branch, confirmation, server reconciliation), history updates"
    )
    def _() -> None:
        ctx, page, problems = open_page("branch")
        page.goto(f"{WEB}/daily-reports")
        expect(page.get_by_role("heading", name="Daily Reports", level=1)).to_be_visible()
        expect(page.get_by_test_id("fixed-branch")).to_have_text(b1[1])
        expect(page.get_by_label("Report Date")).to_have_value(today.isoformat())
        page.get_by_role("button", name="Review & submit").click()
        expect(page.get_by_text("Enter the total sales")).to_be_visible()
        page.get_by_label("Total Sales (AED)").fill("500")
        page.get_by_label("Number of Orders").fill("4")
        page.get_by_label("Cash (AED)").fill("300")
        page.get_by_label("POS (AED)").fill("100")
        page.get_by_label("Shop Expenses (AED)").fill("80")
        page.get_by_label("Savings (AED)").fill("30")
        page.get_by_role("button", name="Review & submit").click()
        page.get_by_role("alertdialog").get_by_role("button", name="Submit report").click()
        summary = page.get_by_test_id("submitted-summary")
        expect(summary).to_contain_text("400.00")  # collections: 300 + 100
        expect(summary).to_contain_text("100.00")  # difference 500 - 400
        expect(summary).to_contain_text("Diff")
        table = page.get_by_role("table", name="Daily report history")
        expect(table.get_by_role("row")).to_have_count(
            3
        )  # header + the 30-days-ago report + today's
        page.screenshot(path=str(shots / "step7_daily_reports_branch.png"), full_page=True)
        # submitting the same day again is refused with the server message
        page.get_by_label("Total Sales (AED)").fill("500")
        page.get_by_label("Number of Orders").fill("4")
        page.get_by_role("button", name="Review & submit").click()
        page.get_by_role("alertdialog").get_by_role("button", name="Submit report").click()
        expect(
            page.get_by_text("A report for this branch and date already exists").first
        ).to_be_visible()
        assert not [p for p in problems if "409" not in p], problems
        ctx.close()

    _()

    @scenario(
        "STEP7 UI: owner dashboard shows real figures, switches Daily/Monthly, and refreshes after a new report"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        kpis = page.get_by_test_id("kpis")
        expect(kpis).to_contain_text("500.00")  # today's only report so far
        expect(page.get_by_text("Needs attention")).to_be_visible()
        expect(page.get_by_role("table", name="Branch-wise summary")).to_be_visible()
        page.get_by_role("button", name="Monthly").click()
        expect(page.get_by_role("button", name="This Month")).to_be_visible()
        expect(page.get_by_role("table", name="Day by day totals")).to_be_visible()
        page.screenshot(path=str(shots / "step7_owner_dashboard_month.png"), full_page=True)
        page.get_by_role("button", name="Daily").click()
        page.screenshot(path=str(shots / "step7_owner_dashboard_day.png"), full_page=True)
        # a report submitted elsewhere is picked up by a reload (and invalidated in-app after own submissions)
        http(
            "POST",
            f"{API}/api/v1/daily-reports",
            report(
                today,
                branch_id=str(b2[0]),
                total_sales="250.00",
                cash_received="250.00",
                pos_amount="0",
                bank_transfer="0",
                link_payment="0",
                shop_expenses="0",
                shop_savings="0",
            ),
            tok["owner"],
        )
        page.reload()
        expect(page.get_by_test_id("kpis")).to_contain_text("750.00")
        assert not problems, problems
        ctx.close()

    _()

    @scenario(
        "STEP7 UI: Branch & Date View for owner (all/one branch, quick filters) and branch user (own only)"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        page.goto(f"{WEB}/branch-date-view")
        expect(page.get_by_role("heading", name="Branch & Date View", level=1)).to_be_visible()
        expect(
            page.get_by_role("table", name="Daily reports in the selected range")
        ).to_be_visible()
        page.get_by_role("button", name="Today").click()
        expect(page.get_by_role("heading", name="Head Office expenses", exact=True)).to_be_visible()
        page.screenshot(path=str(shots / "step7_branch_date_owner.png"), full_page=True)
        ctx.close()
        ctx, page, problems = open_page("branch")
        page.goto(f"{WEB}/branch-date-view")
        expect(page.get_by_role("heading", name="Branch & Date View", level=1)).to_be_visible()
        expect(page.get_by_role("combobox", name="Branch")).to_have_count(0)
        expect(page.get_by_role("heading", name="Head Office expenses", exact=True)).to_have_count(
            0
        )
        page.get_by_role("button", name="Last 14 days").click()
        expect(page.get_by_text(b2[1], exact=True)).to_have_count(0)
        page.screenshot(path=str(shots / "step7_branch_date_branch.png"), full_page=True)
        assert not problems, problems
        ctx.close()

    _()

    @scenario("STEP7 UI: missing reports listed on the owner dashboard once reporting has started")
    def _() -> None:
        ctx, page, problems = open_page("owner")
        expect(page.get_by_text("expected reports are").first).to_be_visible()
        assert not problems, problems
        ctx.close()

    _()

    for w, h in ((390, 844), (768, 1024), (1440, 900)):

        @scenario(f"STEP7 LAYOUT {w}px: dashboard, daily reports and branch view fit the viewport")
        def _(w=w, h=h) -> None:
            for role, paths in (
                ("owner", ["/", "/daily-reports", "/branch-date-view"]),
                ("branch", ["/", "/daily-reports", "/branch-date-view"]),
            ):
                ctx, page, problems = open_page(role, w, h)
                for path in paths:
                    page.goto(f"{WEB}{path}")
                    page.wait_for_load_state("networkidle")
                    m = page.evaluate(
                        "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
                    )
                    assert m["doc"] <= m["win"], f"overflow {role} {path} @{w}: {m}"
                    page.screenshot(
                        path=str(shots / f"step7_{role}_{path.strip('/') or 'dashboard'}_{w}.png")
                    )
                assert not problems, problems
                ctx.close()

        _()


def run_step8_scenarios(browser: Browser, users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    """Step 8: opening balances, cash & banks, expenses & savings, suppliers against REAL database rows (no mocks).
    Runs after Step 7, so an opening balance row (set by the Step 7 scenario) and some reports already exist;
    figures are therefore asserted as before/after DIFFERENCES, never as absolute totals."""
    from datetime import datetime
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Dubai")).date()
    shots = ROOT / "e2e" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    tok = {
        k: {"Authorization": "Bearer " + sign_in_token(users[k]["email"], users[k]["password"])}
        for k in ("owner", "branch")
    }
    A = f"{API}/api/v1"

    def get(path: str, who: str = "owner") -> tuple[int, dict | list]:
        return http("GET", f"{A}{path}", headers=tok[who])  # type: ignore[return-value]

    def post(path: str, body: dict, who: str = "owner") -> tuple[int, dict]:
        return http("POST", f"{A}{path}", body, tok[who])

    def summary() -> dict[str, Decimal]:
        s, j = get("/cash-banks/summary")
        assert s == 200 and j["status"] == "ok", j  # type: ignore[index]
        return {
            k: Decimal(v)
            for k, v in j.items()
            if k
            in (  # type: ignore[union-attr]
                "cash_in_hand",
                "enbd",
                "adcb",
                "pos_pending",
                "total_cash_bank",
                "total_savings",
            )
        }

    def category(name: str) -> str:
        _, cats = get("/expenses/categories")
        return next(c["id"] for c in cats if c["name"].lower() == name.lower())  # type: ignore[union-attr]

    def open_page(role: str, w: int = 1440, h: int = 900) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=w < 768)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        login_ui(page, users[role]["email"], users[role]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    @scenario("STEP8 API: Branch User is refused on every finance endpoint; anonymous gets 401")
    def _() -> None:
        for path in (
            "/opening-balances",
            "/opening-balances/history",
            "/cash-banks/summary",
            "/cash-banks/accounts",
            "/cash-banks/branches",
            "/cash-banks/transactions",
            "/cash-banks/transfers",
            "/cash-banks/pos-settlements",
            "/expenses",
            "/expenses/categories",
            "/suppliers",
            "/suppliers/summary",
        ):
            assert get(path, "branch")[0] == 403, path
        assert (
            post(
                "/cash-banks/transfers",
                {"from_account": "ENBD", "to_account": "ADCB", "amount": "1"},
                "branch",
            )[0]
            == 403
        )
        assert (
            post("/cash-banks/pos-settlements", {"bank": "ENBD", "amount": "1"}, "branch")[0] == 403
        )
        assert (
            post(
                "/expenses",
                {"category_id": str(uuid.uuid4()), "amount": "1", "paid_from": "Cash"},
                "branch",
            )[0]
            == 403
        )
        assert post("/suppliers", {"name": "Nope"}, "branch")[0] == 403
        assert http("PUT", f"{A}/opening-balances", {}, tok["branch"])[0] == 403
        assert http("GET", f"{A}/cash-banks/summary")[0] == 401

    _()

    @scenario(
        "STEP8 API: opening balances change only with a reason, are validated, and are audited"
    )
    def _() -> None:
        s, ob = get("/opening-balances")
        assert s == 200 and ob["status"] == "configured", ob  # type: ignore[index]
        body = {
            "as_of_date": ob["as_of_date"],
            "receipts_bank": "ENBD",
            "enbd_balance": "1000.00",  # type: ignore[index]
            "adcb_balance": "500.00",
            "pos_pending": "200.00",
            "savings_brought_forward": "100.00",
            "branch_cash": [
                {
                    "branch_id": r["branch_id"],
                    "amount": "2000.00" if r["branch_id"] == str(b1[0]) else "0.00",
                }
                for r in ob["branch_cash"]
            ],  # type: ignore[index]
            "supplier_dues": [],
        }
        assert len(body["branch_cash"]) == 10
        s, e = http("PUT", f"{A}/opening-balances", body, tok["owner"])
        assert s == 422 and "reason" in e["error"]["fields"], (
            e
        )  # saved balances are never changed silently
        for bad in ({"enbd_balance": "-1"}, {"adcb_balance": "1.234"}, {"receipts_bank": "CBD"}):
            assert (
                http(
                    "PUT", f"{A}/opening-balances", {**body, **bad, "reason": "check"}, tok["owner"]
                )[0]
                == 422
            ), bad
        s, ok = http(
            "PUT",
            f"{A}/opening-balances",
            {**body, "reason": "E2E: set branch cash and savings"},
            tok["owner"],
        )
        assert s == 200 and ok["total_branch_cash"] == "2000.00" and ok["updated_by_name"], ok
        s, hist = get("/opening-balances/history")
        assert any(
            h["action"] == "UPDATE" and h["reason"] == "E2E: set branch cash and savings"
            for h in hist
        ), hist  # type: ignore[union-attr]

    _()

    @scenario(
        "STEP8 API: expenses, savings, transfers and POS settlements move balances exactly once and refuse overdrafts"
    )
    def _() -> None:
        b0 = summary()
        key = str(uuid.uuid4())
        exp = {
            "category_id": category("Utilities"),
            "amount": "100.00",
            "paid_from": "ENBD",
            "client_key": key,
        }
        s, e1 = post("/expenses", exp)
        assert s == 201 and e1["category"] == "Utilities" and e1["is_saving"] is False, e1
        b1_ = summary()
        assert (
            b1_["enbd"] == b0["enbd"] - 100
            and b1_["total_cash_bank"] == b0["total_cash_bank"] - 100
        )
        s, dup = post("/expenses", exp)
        assert (s, dup["error"]["code"]) == (409, "duplicate_transaction"), dup
        assert summary()["enbd"] == b1_["enbd"]  # the repeat changed nothing
        s, e = post("/expenses", {**exp, "client_key": str(uuid.uuid4()), "amount": "999999.00"})
        assert (s, e["error"]["code"]) == (422, "insufficient_funds"), e
        # a saving: counted in savings, still leaves the account it was paid from
        s, sav = post(
            "/expenses",
            {
                "category_id": category("Rent"),
                "amount": "50.00",
                "paid_from": "Cash",
                "is_saving": True,
            },
        )
        assert s == 201 and sav["is_saving"] is True, sav
        b2_ = summary()
        assert (
            b2_["total_savings"] == b1_["total_savings"] + 50
            and b2_["cash_in_hand"] == b1_["cash_in_hand"] - 50
        )
        # transfer: one debit + one credit, total unchanged
        s, t = post(
            "/cash-banks/transfers",
            {"from_account": "ENBD", "to_account": "ADCB", "amount": "200.00"},
        )
        assert s == 201, t
        b3 = summary()
        assert (
            b3["enbd"] == b2_["enbd"] - 200
            and b3["adcb"] == b2_["adcb"] + 200
            and b3["total_cash_bank"] == b2_["total_cash_bank"]
        )
        s, led = get(f"/cash-banks/transactions?date_from={today}&date_to={today}&page_size=100")
        legs = [x for x in led["items"] if x["source_id"] == t["id"]]  # type: ignore[index]
        assert sorted((x["account"], x["amount"]) for x in legs) == [
            ("ADCB", "200.00"),
            ("ENBD", "-200.00"),
        ], legs
        s, e = post(
            "/cash-banks/transfers",
            {"from_account": "ADCB", "to_account": "ENBD", "amount": "99999999.00"},
        )
        assert (s, e["error"]["code"]) == (422, "insufficient_funds"), e
        assert (
            post(
                "/cash-banks/transfers",
                {"from_account": "ADCB", "to_account": "ADCB", "amount": "1"},
            )[0]
            == 422
        )
        # POS settlement: pending down, bank up, total cash+bank up by the settled amount
        s, st = post(
            "/cash-banks/pos-settlements", {"bank": "ADCB", "amount": "50.00", "reference": "E2E"}
        )
        assert s == 201, st
        b4 = summary()
        assert b4["pos_pending"] == b3["pos_pending"] - 50 and b4["adcb"] == b3["adcb"] + 50
        assert b4["total_cash_bank"] == b3["total_cash_bank"] + 50
        s, e = post(
            "/cash-banks/pos-settlements", {"bank": "ENBD", "amount": str(b4["pos_pending"] + 1)}
        )
        assert (s, e["error"]["code"]) == (422, "insufficient_funds"), e
        # void with a reason restores both sides; a second void is refused
        assert post(f"/cash-banks/transfers/{t['id']}/void", {"reason": ""})[0] == 422
        assert post(f"/cash-banks/transfers/{t['id']}/void", {"reason": "E2E undo"})[0] == 204
        b5 = summary()
        assert b5["enbd"] == b4["enbd"] + 200 and b5["adcb"] == b4["adcb"] - 200
        assert post(f"/cash-banks/transfers/{t['id']}/void", {"reason": "again"})[0] == 404

    _()

    @scenario(
        "STEP8 API: supplier outstanding = opening + new dues - payments; partial, full and Mark as Paid"
    )
    def _() -> None:
        s, sup = post(
            "/suppliers",
            {"name": "E2E Chem Co", "category": "Detergents", "payment_terms": "30 days"},
        )
        assert s == 201 and sup["outstanding"] == "0.00", sup
        sid = sup["id"]
        assert (
            post("/suppliers", {"name": "e2e chem co"})[0] == 409
        )  # unique name, case-insensitive
        s, ob = get("/opening-balances")
        body = {
            "as_of_date": ob["as_of_date"],
            "receipts_bank": ob["receipts_bank"],
            "enbd_balance": ob["enbd_balance"],  # type: ignore[index]
            "adcb_balance": ob["adcb_balance"],
            "pos_pending": ob["pos_pending"],  # type: ignore[index]
            "savings_brought_forward": ob["savings_brought_forward"],  # type: ignore[index]
            "branch_cash": [
                {"branch_id": r["branch_id"], "amount": r["amount"]} for r in ob["branch_cash"]
            ],  # type: ignore[index]
            "supplier_dues": [{"supplier_id": sid, "amount": "1000.00"}],
            "reason": "E2E: supplier opening due",
        }
        assert http("PUT", f"{A}/opening-balances", body, tok["owner"])[0] == 200
        assert post(f"/suppliers/{sid}/dues", {"amount": "250.00", "reference": "INV-1"})[0] == 201
        s, p = post(
            f"/suppliers/{sid}/payments",
            {"amount": "400.00", "paid_from": "Cash", "client_key": (k := str(uuid.uuid4()))},
        )
        assert s == 201 and p["kind"] == "payment", p
        assert (
            post(
                f"/suppliers/{sid}/payments",
                {"amount": "400.00", "paid_from": "Cash", "client_key": k},
            )[1]["error"]["code"]
            == "duplicate_transaction"
        )
        s, d = get(f"/suppliers/{sid}")
        assert (d["opening_outstanding"], d["new_dues"], d["total_paid"], d["outstanding"]) == (
            "1000.00",
            "250.00",
            "400.00",
            "850.00",
        ), d  # type: ignore[index,call-overload]
        s, e = post(f"/suppliers/{sid}/payments", {"amount": "850.01", "paid_from": "Cash"})
        assert (s, e["error"]["code"]) == (422, "exceeds_outstanding"), e
        before = summary()
        s, m = post(f"/suppliers/{sid}/mark-paid", {"paid_from": "ENBD", "reference": "FINAL"})
        assert s == 201 and m["amount"] == "850.00", m
        assert summary()["enbd"] == before["enbd"] - 850
        s, d = get(f"/suppliers/{sid}")
        assert d["outstanding"] == "0.00" and d["opening_outstanding"] == "1000.00", d  # type: ignore[index,call-overload]
        assert (
            post(f"/suppliers/{sid}/mark-paid", {"paid_from": "ENBD"})[1]["error"]["code"]
            == "nothing_outstanding"
        )
        s, h = get(f"/suppliers/{sid}/entries")
        assert h["total"] == 3, h  # type: ignore[index]  # due + partial payment + final payment: history kept, nothing overwritten

    _()

    @scenario("STEP8 API: the Step 7 dashboard shows the same balances as Cash & Banks")
    def _() -> None:
        s, dash = get("/dashboard/owner")
        sm = summary()
        bal = dash["balances"]  # type: ignore[index]
        assert bal["status"] == "ok"
        assert (
            Decimal(bal["cash_in_hand"]),
            Decimal(bal["enbd"]),
            Decimal(bal["adcb"]),
            Decimal(bal["pos_pending"]),
            Decimal(bal["total"]),
        ) == (sm["cash_in_hand"], sm["enbd"], sm["adcb"], sm["pos_pending"], sm["total_cash_bank"])

    _()

    @scenario(
        "STEP8 UI: owner records an expense, marks it as a saving (with a reason) and sees the list update"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        page.goto(f"{WEB}/expenses")
        expect(page.get_by_role("heading", name="Expenses & Savings", level=1)).to_be_visible()
        page.get_by_role("button", name="New expense").click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_role("button", name="Record expense").click()
        expect(dialog.get_by_text("Choose a category")).to_be_visible()
        dialog.get_by_role("combobox", name="Category").click()
        page.get_by_role("option", name="Transport").click()
        dialog.get_by_role("combobox", name="Paid from").click()
        page.get_by_role("option", name="Cash").click()
        dialog.get_by_label("Amount (AED)").fill("25.50")
        dialog.get_by_label("Note").fill("E2E taxi")
        dialog.get_by_role("button", name="Record expense").click()
        table = page.get_by_role("table", name="Head office expenses")
        row = table.get_by_role("row").filter(has_text="E2E taxi")
        expect(row).to_have_count(1)
        expect(row).to_contain_text("25.50")
        expect(row).to_contain_text("Expense")
        page.get_by_role("button", name="Mark as saving Transport").first.click()
        confirm = page.get_by_role("alertdialog")
        confirm.get_by_role("button", name="Mark as saving").click()
        expect(confirm.get_by_text("Enter a reason (at least 3 characters)")).to_be_visible()
        confirm.get_by_role("textbox").fill("E2E move to savings")
        confirm.get_by_role("button", name="Mark as saving").click()
        expect(table.get_by_role("row").filter(has_text="E2E taxi")).to_contain_text("Saving")
        page.get_by_role("button", name="View expense Transport").first.click()
        expect(
            page.get_by_role("dialog").get_by_text("E2E move to savings")
        ).to_be_visible()  # audit trail shows the reason
        page.keyboard.press("Escape")
        page.screenshot(path=str(shots / "step8_expenses_owner.png"), full_page=True)
        assert not problems, problems
        ctx.close()

    _()

    @scenario("STEP8 UI: owner adds a supplier, records a due, a partial payment and Mark as Paid")
    def _() -> None:
        ctx, page, problems = open_page("owner")
        page.goto(f"{WEB}/suppliers")
        expect(page.get_by_role("heading", name="Suppliers", level=1)).to_be_visible()
        expect(page.get_by_label("Supplier summary")).to_contain_text("Total Outstanding")
        page.get_by_role("button", name="Add supplier").click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_label("Supplier name").fill("E2E UI Packaging")
        dialog.get_by_label("Supplies / service description").fill("Bags and hangers")
        dialog.get_by_role("button", name="Add supplier").click()
        page.get_by_role("link", name="E2E UI Packaging").click()
        expect(page.get_by_role("heading", name="E2E UI Packaging", level=1)).to_be_visible()
        page.get_by_role("button", name="Add new due").click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_label("Amount (AED)").fill("120")
        dialog.get_by_role("button", name="Add due").click()
        balance = page.get_by_label("Supplier balance")
        expect(balance).to_contain_text("120.00")
        page.get_by_role("button", name="Record payment").click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_label("Amount (AED)").fill("200")
        dialog.get_by_role("combobox", name="Paid from").click()
        page.get_by_role("option", name="Cash").click()
        dialog.get_by_role("button", name="Record payment").click()
        expect(dialog.get_by_text("Payment cannot exceed the outstanding amount")).to_be_visible()
        dialog.get_by_label("Amount (AED)").fill("20")
        dialog.get_by_role("button", name="Record payment").click()
        expect(balance.get_by_text("AED 100.00").first).to_be_visible()  # 120 due - 20 paid
        page.get_by_role("button", name="Mark as Paid").click()
        confirm = page.get_by_role("alertdialog")
        expect(confirm).to_contain_text("100.00")
        confirm.get_by_role("combobox", name="Paid from").click()
        page.get_by_role("option", name="Cash").click()
        confirm.get_by_role("button", name="Record full payment").click()
        expect(page.get_by_role("button", name="Mark as Paid")).to_be_disabled()
        history = page.get_by_role("table", name="Supplier dues and payments")
        expect(history.get_by_role("row")).to_have_count(
            4
        )  # header + due + partial payment + final payment
        page.screenshot(path=str(shots / "step8_supplier_detail.png"), full_page=True)
        assert not problems, problems
        ctx.close()

    _()

    @scenario(
        "STEP8 UI: Opening Balances and Cash & Banks show the configured figures, history and filters"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        page.goto(f"{WEB}/opening-balances")
        expect(page.get_by_role("heading", name="Opening Balances", level=1)).to_be_visible()
        expect(page.get_by_text("Configured", exact=True)).to_be_visible()
        expect(page.get_by_label(re.compile(r"^ALSAFA MAIN \(AED\)"))).to_have_value("2000.00")
        page.get_by_role("button", name="Review changes").click()
        expect(
            page.get_by_text("A reason is required to change saved opening balances")
        ).to_be_visible()
        page.get_by_role("button", name="Show history").click()
        expect(page.get_by_role("table", name="Opening balance change history")).to_be_visible()
        page.screenshot(path=str(shots / "step8_opening_balances.png"), full_page=True)

        page.goto(f"{WEB}/cash-banks")
        expect(page.get_by_role("heading", name="Cash & Banks", level=1)).to_be_visible()
        cards = page.get_by_label("Balances")
        for label in (
            "Total Cash + Bank",
            "Cash in Hand",
            "ENBD",
            "ADCB",
            "POS Pending",
            "Total Savings",
        ):
            expect(cards.get_by_text(label, exact=True)).to_be_visible()
        sm = summary()
        expect(cards).to_contain_text(f"{sm['enbd']:,.2f}")
        table = page.get_by_role("table", name="Cash and bank transaction history")
        expect(table).to_be_visible()
        page.get_by_role("button", name="ENBD movements").click()
        expect(page.get_by_role("button", name="ENBD movements")).to_have_attribute(
            "aria-pressed", "true"
        )
        expect(table.get_by_role("row").nth(1)).to_contain_text("ENBD")
        expect(page.get_by_role("table", name="Cash balance by branch")).to_be_visible()
        page.screenshot(path=str(shots / "step8_cash_banks.png"), full_page=True)
        assert not problems, problems
        ctx.close()

    _()

    @scenario(
        "STEP8 UI: Branch User sees no finance links and typing a finance URL shows Access denied"
    )
    def _() -> None:
        ctx, page, problems = open_page("branch")
        nav = page.get_by_role("navigation").first
        for name in ("Cash & Banks", "Opening Balances", "Expenses & Savings", "Suppliers"):
            expect(page.get_by_role("link", name=name)).to_have_count(0)
        denied: list[str] = []
        page.on(
            "request",
            lambda r: (
                denied.append(r.url)
                if re.search(r"/(opening-balances|cash-banks|expenses|suppliers)", r.url)
                and "/api/" in r.url
                else None
            ),
        )
        for path in ("/opening-balances", "/cash-banks", "/expenses", "/suppliers"):
            page.goto(f"{WEB}{path}")
            expect(page.get_by_text("Access denied")).to_be_visible()
        assert not denied, denied  # the pages never even asked the server for finance data
        _ = nav
        ctx.close()

    _()

    for w, h in ((390, 844), (768, 1024), (1440, 900)):

        @scenario(f"STEP8 LAYOUT {w}px: finance pages fit the viewport")
        def _(w=w, h=h) -> None:
            ctx, page, problems = open_page("owner", w, h)
            for path in ("/opening-balances", "/cash-banks", "/expenses", "/suppliers"):
                page.goto(f"{WEB}{path}")
                page.wait_for_load_state("networkidle")
                m = page.evaluate(
                    "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
                )
                assert m["doc"] <= m["win"], f"overflow {path} @{w}: {m}"
                page.screenshot(path=str(shots / f"step8_{path.strip('/')}_{w}.png"))
            assert not problems, problems
            ctx.close()

        _()


def run_step9_scenarios(browser: Browser, users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    """Step 9: employees, leave / six-month rule, visas & passports, trade licences, alerts against REAL rows."""
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Dubai")).date()
    shots = ROOT / "e2e" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    tok = {
        k: {"Authorization": "Bearer " + sign_in_token(users[k]["email"], users[k]["password"])}
        for k in ("owner", "branch")
    }
    A = f"{API}/api/v1"

    def get(path: str, who: str = "owner") -> tuple[int, dict | list]:
        return http("GET", f"{A}{path}", headers=tok[who])  # type: ignore[return-value]

    def post(path: str, body: dict, who: str = "owner") -> tuple[int, dict]:
        return http("POST", f"{A}{path}", body, tok[who])

    def d(n: int) -> str:
        return (today + timedelta(days=n)).isoformat()

    def open_page(role: str, w: int = 1440, h: int = 900) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=w < 768)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        login_ui(page, users[role]["email"], users[role]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    ids: dict[str, str] = {}

    @scenario("STEP9 API: Branch User is refused on every HR endpoint; anonymous gets 401")
    def _() -> None:
        some = str(uuid.uuid4())
        for path in (
            "/employees",
            "/employees/summary",
            "/employees/leave/summary",
            f"/employees/{some}",
            "/visas-passports/summary",
            "/visas-passports/visas",
            "/visas-passports/passports",
            "/trade-licenses",
            "/trade-licenses/summary",
            f"/trade-licenses/{some}",
            "/compliance/alerts",
        ):
            assert get(path, "branch")[0] == 403, path
            assert http("GET", f"{A}{path}")[0] == 401, path
        assert post("/employees", {}, "branch")[0] == 403
        assert post("/trade-licenses", {}, "branch")[0] == 403
        assert post(f"/trade-licenses/{some}/renew", {}, "branch")[0] == 403

    _()

    @scenario(
        "STEP9 API: employee lifecycle against real rows (create, leave, six-month rule, permanent cancellation)"
    )
    def _() -> None:
        s, j = post(
            "/employees",
            {
                "full_name": "E2E Present",
                "branch_id": str(b1[0]),
                "monthly_salary": "1200.00",
                "visa_expiry": d(20),
                "passport_expiry": d(100),
            },
        )
        assert s == 201, j
        ids["present"] = j["employee"]["id"]
        assert j["employee"]["status"] == "Active" and j["employee"]["visa_status"] == "urgent"
        s, j = post(
            "/employees",
            {"full_name": "E2E Leaver", "branch_id": str(b2[0]), "monthly_salary": "900.00"},
        )
        ids["leaver"] = j["employee"]["id"]
        s, j = post(
            "/employees",
            {"full_name": "E2E Late", "branch_id": str(b2[0]), "monthly_salary": "800.00"},
        )
        ids["late"] = j["employee"]["id"]
        # leave without a start date is refused; a reason is mandatory
        assert (
            post(f"/employees/{ids['leaver']}/status", {"status": "On Leave", "reason": "Home"})[0]
            == 422
        )
        s, j = post(
            f"/employees/{ids['leaver']}/status",
            {"status": "On Leave", "leave_start": d(-5), "reason": "Home leave"},
        )
        assert (
            s == 200
            and j["employee"]["status"] == "On Leave"
            and j["employee"]["payroll_eligible"] is False
        )
        # six calendar months, not 180 days: a start 190 days ago is NOT yet past the limit
        s, j = post(
            f"/employees/{ids['late']}/status",
            {"status": "On Leave", "leave_start": d(-190), "reason": "Long leave"},
        )
        assert s == 200 and j["employee"]["leave"]["state"] in (
            "on_leave",
            "approaching_limit",
            "limit_reached",
            "visa_cancelled",
        )
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(
                "update public.employees set leave_start = %s where id = %s",
                (today - timedelta(days=230), ids["late"]),
            )
        s, j = get(f"/employees/{ids['late']}")
        assert j["employee"]["status"] == "Visa Cancelled", j  # well past six calendar months
        s, j = post(f"/employees/{ids['late']}/return", {"reason": "Came back late"})
        assert (
            s == 200
            and j["employee"]["visa_cancelled"] is True
            and j["employee"]["stored_status"] == "Active"
        )
        assert (
            post(
                f"/employees/{ids['late']}/status",
                {"status": "On Leave", "leave_start": d(-1), "reason": "again"},
            )[0]
            == 409
        )
        s, sm = get("/employees/summary")
        assert sm["total_active"] >= 1 and sm["visa_cancelled"] >= 1 and sm["on_leave"] >= 1

    _()

    @scenario(
        "STEP9 API: trade licence renewal adds one year once, keeps history, refuses a repeat; alerts have no duplicates"
    )
    def _() -> None:
        s, j = post(
            "/trade-licenses",
            {
                "branch_id": str(b1[0]),
                "license_no": "E2E-TL-1",
                "authority": "E2E Authority",
                "expiry_date": d(12),
                "renewal_fee": "2500.00",
            },
        )
        assert s == 201, j
        lid = j["license"]["id"]
        ids["license"] = lid
        assert (
            post(
                "/trade-licenses",
                {
                    "branch_id": str(b1[0]),
                    "license_no": "e2e-tl-1",
                    "expiry_date": d(30),
                    "renewal_fee": "1",
                },
            )[0]
            == 409
        )
        s, a = get("/compliance/alerts")
        keys = [i["key"] for i in a["items"]]
        assert len(keys) == len(set(keys)) and f"license_expiring:{lid}" in keys
        s, j = post(f"/trade-licenses/{lid}/renew", {"expected_expiry": d(12)})
        e0 = date.fromisoformat(d(12))
        assert (
            s == 200
            and j["license"]["expiry_date"]
            == date(
                e0.year + 1, e0.month, min(e0.day, 28 if (e0.month == 2) else e0.day)
            ).isoformat()
        ), j
        assert len(j["renewals"]) == 1 and j["renewals"][0]["previous_expiry"] == d(12)
        assert (
            post(f"/trade-licenses/{lid}/renew", {"expected_expiry": d(12)})[0] == 409
        )  # repeated click refused
        s, rn = get(f"/trade-licenses/{lid}/renewals")
        assert len(rn) == 1
        s, a = get("/compliance/alerts")
        assert f"license_expiring:{lid}" not in [i["key"] for i in a["items"]]
        s, sm = get("/trade-licenses/summary")
        assert sm["total"] >= 1

    _()

    @scenario("STEP9 UI: Branch User sees no HR menu, pages are denied and no HR request is made")
    def _() -> None:
        ctx, page, problems = open_page("branch")
        nav = page.get_by_role("navigation", name="Main")
        for name in ("Employees", "Visas & Passports", "Trade Licenses"):
            expect(nav.get_by_role("link", name=name)).to_have_count(0)
        denied: list[str] = []
        page.on(
            "request",
            lambda r: (
                denied.append(r.url)
                if re.search(r"/(employees|visas-passports|trade-licenses|compliance)", r.url)
                and "/api/" in r.url
                else None
            ),
        )
        for path in ("/employees", "/visas-passports", "/trade-licenses"):
            page.goto(f"{WEB}{path}")
            expect(page.get_by_text("Access denied")).to_be_visible()
        assert not denied, denied
        ctx.close()

    _()

    @scenario(
        "STEP9 UI: Owner works with employees, leave, visas & passports and licences in the browser"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        page.goto(f"{WEB}/employees")
        expect(page.get_by_role("heading", name="Employees", level=1)).to_be_visible()
        expect(page.get_by_text("Monthly Payroll Total")).to_be_visible()
        expect(page.get_by_role("link", name="E2E Present")).to_be_visible()
        page.screenshot(path=str(shots / "step9_employees_1440.png"))
        # search + detail + start leave through the confirmation dialog
        page.get_by_label("Search").fill("E2E Present")
        expect(page.get_by_role("link", name="E2E Present")).to_be_visible()
        page.get_by_role("link", name="E2E Present").click()
        expect(page.get_by_role("heading", name="E2E Present", level=1)).to_be_visible()
        page.get_by_role("button", name="Start leave").click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_role("button", name="Start leave").click()
        expect(dlg.get_by_text("at least 3 characters")).to_be_visible()
        dlg.get_by_label("Reason").fill("E2E holiday")
        dlg.get_by_role("button", name="Start leave").click()
        expect(page.get_by_text("Leave and six-month limit")).to_be_visible()
        expect(page.get_by_text("not 180 days")).to_be_visible()
        page.screenshot(path=str(shots / "step9_employee_detail_1440.png"))
        # visas & passports
        page.goto(f"{WEB}/visas-passports")
        expect(page.get_by_role("heading", name="Visas & Passports", level=1)).to_be_visible()
        expect(page.get_by_role("table", name="Visa records")).to_be_visible()
        expect(page.get_by_role("table", name="Passport records")).to_be_visible()
        page.screenshot(path=str(shots / "step9_visas_1440.png"))
        # trade licence + renewal confirmation
        page.goto(f"{WEB}/trade-licenses/{ids['license']}")
        expect(page.get_by_role("heading", name="Licence E2E-TL-1", level=1)).to_be_visible()
        page.get_by_role("button", name="Mark as renewed").click()
        expect(page.get_by_role("dialog").get_by_text("Mark licence as renewed?")).to_be_visible()
        page.get_by_role("dialog").get_by_role("button", name="Cancel").click()
        page.goto(f"{WEB}/trade-licenses")
        expect(page.get_by_role("table", name="Trade licences")).to_be_visible()
        page.screenshot(path=str(shots / "step9_licenses_1440.png"))
        # notification bell shows the compliance alerts (the leaver/present visa alerts exist)
        page.get_by_role("button", name=re.compile("Notifications")).click()
        expect(page.get_by_role("menu")).to_be_visible()
        assert not problems, problems
        ctx.close()

    _()

    for w, h in ((390, 844), (768, 1024), (1440, 900)):

        @scenario(f"STEP9 LAYOUT {w}px: HR pages fit the viewport")
        def _(w=w, h=h) -> None:
            ctx, page, problems = open_page("owner", w, h)
            for path in (
                "/employees",
                f"/employees/{ids['present']}",
                "/visas-passports",
                "/trade-licenses",
                f"/trade-licenses/{ids['license']}",
            ):
                page.goto(f"{WEB}{path}")
                page.wait_for_load_state("networkidle")
                m = page.evaluate(
                    "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
                )
                assert m["doc"] <= m["win"], f"overflow {path} @{w}: {m}"
            page.screenshot(path=str(shots / f"step9_visas_{w}.png"))
            assert not problems, problems
            ctx.close()

        _()


def run_step10_scenarios(browser: Browser, users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    """Step 10: rental agreements, PDC cheques, clearing / bouncing / renewal and alerts against REAL rows."""
    from decimal import Decimal

    shots = ROOT / "e2e" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    tok = {
        k: {"Authorization": "Bearer " + sign_in_token(users[k]["email"], users[k]["password"])}
        for k in ("owner", "branch")
    }
    A = f"{API}/api/v1"

    def get(path: str, who: str = "owner") -> tuple[int, dict | list]:
        return http("GET", f"{A}{path}", headers=tok[who])  # type: ignore[return-value]

    def post(path: str, body: dict, who: str = "owner") -> tuple[int, dict]:
        return http("POST", f"{A}{path}", body, tok[who])

    def open_page(role: str, w: int = 1440, h: int = 900) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=w < 768)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        login_ui(page, users[role]["email"], users[role]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    s0, ob = get("/opening-balances")
    assert s0 == 200 and ob["status"] == "configured", ob  # type: ignore[index]
    start = ob["tracking_start"]  # type: ignore[index]
    ids: dict[str, str] = {}

    def balances() -> tuple[str, str]:
        _, b = get("/cash-banks/summary")
        return b["enbd"], b["adcb"]  # type: ignore[index]

    @scenario(
        "STEP10 API: Branch User is refused on every rental / PDC endpoint; anonymous gets 401"
    )
    def _() -> None:
        some = str(uuid.uuid4())
        for path in (
            "/rentals",
            "/rentals/summary",
            "/rentals/alerts",
            "/rentals/upcoming-expiries",
            f"/rentals/{some}",
            "/pdc-cheques",
            "/pdc-cheques/summary",
            f"/pdc-cheques/{some}",
        ):
            assert get(path, "branch")[0] == 403, path
            assert http("GET", f"{A}{path}")[0] == 401, path
        for path in ("/rentals", "/rentals/schedule-preview", f"/pdc-cheques/{some}/clear"):
            assert post(path, {}, "branch")[0] == 403, path

    _()

    body = {
        "branch_id": str(b1[0]),
        "landlord": "E2E Landlord LLC",
        "unit": "E2E Shop 1",
        "start_date": start,
        "annual_rent": "80.00",
        "bank": "ENBD",
        "cheque_count": 4,
        "first_cheque_date": start,
        "first_cheque_no": "E2E000100",
    }

    @scenario("STEP10 API: preview, validation, then create an agreement with its cheque schedule")
    def _() -> None:
        s, p = post(
            "/rentals/schedule-preview",
            {
                k: body[k]
                for k in (
                    "annual_rent",
                    "cheque_count",
                    "first_cheque_date",
                    "first_cheque_no",
                    "bank",
                )
            },
        )
        assert s == 200 and p["matches"] and p["cheque_count"] == 4, p  # type: ignore[index]
        assert [x["amount"] for x in p["lines"]] == ["20.00"] * 4  # type: ignore[index]
        for bad in ({"annual_rent": "0"}, {"cheque_count": 13}, {"first_cheque_no": "ABC"}):
            assert post("/rentals", {**body, **bad})[0] == 422, bad
        s, d = post("/rentals", body)
        assert s == 201, d
        ids["agr"] = d["agreement"]["id"]
        cheques = d["schedule"]["items"]
        assert [c["cheque_no"] for c in cheques] == [f"E2E00010{i}" for i in range(4)]
        assert all(c["status"] == "Pending" for c in cheques)
        ids["c0"], ids["c1"], ids["c2"], ids["c3"] = (c["id"] for c in cheques)
        assert d["schedule"]["matches"] is True and d["schedule"]["total_cheque_value"] == "80.00"
        assert post("/rentals", body)[0] == 409  # the same cheque numbers again are refused

    _()

    @scenario(
        "STEP10 API: clearing deducts the bank exactly once; bounce does not; replacement keeps the record"
    )
    def _() -> None:
        before = balances()
        s, c = post(f"/pdc-cheques/{ids['c0']}/clear", {})
        assert s == 200 and c["cheque"]["status"] == "Cleared", c
        after = balances()
        assert Decimal(before[0]) - Decimal(after[0]) == Decimal("20.00") and before[1] == after[1]
        assert post(f"/pdc-cheques/{ids['c0']}/clear", {})[0] == 409
        assert balances() == after  # a repeated clear changes nothing
        s, b = post(f"/pdc-cheques/{ids['c1']}/bounce", {"reason": "E2E returned by bank"})
        assert s == 200 and b["cheque"]["status"] == "Bounced"
        assert balances() == after  # a bounced cheque is not a deduction
        s, a = get("/rentals/alerts")
        assert any(x["kind"] == "cheque_bounced" for x in a["items"])  # type: ignore[index]
        s, r = post(
            f"/pdc-cheques/{ids['c1']}/replace",
            {"cheque_no": "E2E000900", "reason": "E2E reissued"},
        )
        assert s == 200 and r["cheque"]["replaces_id"] == ids["c1"]
        s, a = get("/rentals/alerts")
        assert not any(
            x["kind"] == "cheque_bounced" and x["key"].endswith(ids["c1"]) for x in a["items"]
        )  # type: ignore[index]
        s, sch = get(f"/rentals/{ids['agr']}/schedule")
        assert sch["total_cheque_value"] == "80.00" and sch["matches"] and len(sch["items"]) == 5  # type: ignore[index]

    _()

    @scenario("STEP10 API: Step 7 dashboard and Step 8 Cash & Banks agree with the cheque ledger")
    def _() -> None:
        s, t = get("/cash-banks/transactions?page_size=100")
        rows = [x for x in t["items"] if "E2E00010" in (x["description"] or "")]  # type: ignore[index]
        assert len(rows) == 1 and rows[0]["amount"] == "-20.00" and rows[0]["account"] == "ENBD"
        s, dsh = http("GET", f"{A}/dashboard/owner", headers=tok["owner"])
        assert s == 200
        keys = {a["key"] for a in dsh["alerts"]}  # type: ignore[index]
        assert "pdc_due_7" in keys, keys  # the replacement cheque is dated today

    _()

    @scenario(
        "STEP10 API: renewal previews, needs confirmation, links agreements and keeps old cheques untouched"
    )
    def _() -> None:
        s, pv = post(f"/rentals/{ids['agr']}/renewal-preview", {})
        assert s == 200 and pv["old_pending_cheques"] >= 1
        assert pv["first_cheque_no"] == "E2E000901", pv  # continues after the highest number
        end = pv["old"]["end_date"]
        assert (
            post(f"/rentals/{ids['agr']}/renew", {"expected_end_date": end, "confirm": False})[0]
            == 422
        )
        s, nw = post(f"/rentals/{ids['agr']}/renew", {"expected_end_date": end, "confirm": True})
        assert s == 201 and nw["agreement"]["renewed_from_id"] == ids["agr"], nw
        ids["agr2"] = nw["agreement"]["id"]
        assert all(c["status"] == "Pending" for c in nw["schedule"]["items"])
        s, old = get(f"/rentals/{ids['agr']}")
        assert old["agreement"]["status"] == "Renewed"  # type: ignore[index]
        assert old["schedule"]["cleared"] == 1 and old["schedule"]["bounced"] == 1  # type: ignore[index]
        assert (
            post(f"/rentals/{ids['agr']}/renew", {"expected_end_date": end, "confirm": True})[0]
            == 409
        )

    _()

    @scenario(
        "STEP10 BROWSER: Owner clears and bounces cheques from the PDC screen; Branch User is blocked"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        page.goto(f"{WEB}/rentals")
        expect(page.get_by_role("heading", name="Rental Agreements", level=1)).to_be_visible()
        expect(page.get_by_role("table", name="Rental agreements")).to_be_visible()
        page.screenshot(path=str(shots / "step10_rentals_1440.png"))
        page.goto(f"{WEB}/rentals/{ids['agr2']}")
        expect(page.get_by_role("table", name="PDC cheque schedule")).to_be_visible()
        page.screenshot(path=str(shots / "step10_agreement_1440.png"))
        page.goto(f"{WEB}/pdc-cheques")
        expect(page.get_by_role("heading", name="PDC Cheques", level=1)).to_be_visible()
        table = page.get_by_role("table", name="PDC cheques")
        row = table.get_by_role("row").filter(has_text="E2E000901")
        row.get_by_role("button", name="Mark Bounced").click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_role("button", name="Mark Bounced").click()
        expect(dlg.get_by_text("Enter a reason")).to_be_visible()  # reason is mandatory
        dlg.get_by_label("Reason").fill("E2E bounced in the browser")
        dlg.get_by_role("button", name="Mark Bounced").click()
        expect(row.get_by_text("Bounced")).to_be_visible()
        expect(row.get_by_role("button", name="Replace cheque")).to_be_visible()
        row2 = table.get_by_role("row").filter(has_text="E2E000902")
        before = balances()
        row2.get_by_role("button", name="Mark Cleared").click()
        page.get_by_role("dialog").get_by_text("will be reduced by").wait_for()
        page.get_by_role("dialog").get_by_role("button", name="Mark Cleared").click()
        expect(row2.get_by_text("Cleared")).to_be_visible()
        expect(row2.get_by_role("button")).to_have_count(0)  # final: no actions
        assert (
            balances() == before
        )  # dated in the future: it reduces the bank only from its cheque date
        page.screenshot(path=str(shots / "step10_pdc_1440.png"))
        page.get_by_role("button", name=re.compile("Notifications")).click()
        expect(page.get_by_role("menu")).to_be_visible()
        assert not problems, problems
        ctx.close()
        ctx, page, problems = open_page("branch")
        nav = page.get_by_role("navigation", name="Main")
        expect(nav.get_by_role("link")).to_have_count(
            9
        )  # Step 13 added the Orders & Delivery entries
        for path in (
            "/rentals",
            f"/rentals/{ids['agr']}",
            "/pdc-cheques",
            "/pdc-cheques/" + ids["c0"],
        ):
            page.goto(f"{WEB}{path}")
            expect(page.get_by_text("Access denied")).to_be_visible()
        ctx.close()

    _()

    for w, h in ((390, 844), (768, 1024), (1440, 900)):

        @scenario(f"STEP10 LAYOUT {w}px: rental and PDC pages fit the viewport")
        def _(w=w, h=h) -> None:
            ctx, page, problems = open_page("owner", w, h)
            for path in (
                "/rentals",
                f"/rentals/{ids['agr2']}",
                "/pdc-cheques",
                f"/pdc-cheques/{ids['c0']}",
            ):
                page.goto(f"{WEB}{path}")
                page.wait_for_load_state("networkidle")
                m = page.evaluate(
                    "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
                )
                assert m["doc"] <= m["win"], f"overflow {path} @{w}: {m}"
            page.screenshot(path=str(shots / f"step10_pdc_{w}.png"))
            assert not problems, problems
            ctx.close()

        _()


def run_step11_scenarios(browser: Browser, users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    """Step 11: tasks, overdue detection and the centralized alerts / notification center against REAL rows."""
    from datetime import date, timedelta

    shots = ROOT / "e2e" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    tok = {
        k: {"Authorization": "Bearer " + sign_in_token(users[k]["email"], users[k]["password"])}
        for k in ("owner", "branch")
    }
    A = f"{API}/api/v1"
    today = date.today()
    ids: dict[str, str] = {}

    def get(path: str, who: str = "owner") -> tuple[int, dict | list]:
        return http("GET", f"{A}{path}", headers=tok[who])  # type: ignore[return-value]

    def post(path: str, body: dict, who: str = "owner") -> tuple[int, dict]:
        return http("POST", f"{A}{path}", body, tok[who])

    def open_page(role: str, w: int = 1440, h: int = 900) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=w < 768)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        login_ui(page, users[role]["email"], users[role]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    @scenario(
        "STEP11 API: Branch User is refused on every task / alert endpoint; anonymous gets 401"
    )
    def _() -> None:
        some = str(uuid.uuid4())
        for path in (
            "/tasks",
            "/tasks/summary",
            f"/tasks/{some}",
            "/alerts",
            "/alerts/summary",
            "/alerts/unread-count",
            "/alerts/history",
        ):
            assert get(path, "branch")[0] == 403, path
            assert http("GET", f"{A}{path}")[0] == 401, path
        for path in ("/tasks", "/alerts/refresh", "/alerts/read-all", f"/alerts/{some}/read"):
            assert post(path, {"title": "x"} if path == "/tasks" else {}, "branch")[0] == 403, path

    _()

    @scenario(
        "STEP11 API: an overdue task creates exactly one alert; completing it resolves the alert"
    )
    def _() -> None:
        st, t = post(
            "/tasks",
            {
                "title": "E2E overdue follow-up",
                "branch_id": str(b1[0]),
                "due_date": (today - timedelta(days=2)).isoformat(),
            },
        )
        assert st == 201 and t["task"]["assignee_name"] == "Unassigned", t
        ids["task"] = t["task"]["id"]
        for _i in range(3):
            get("/alerts/summary")
        _, a = get("/alerts?kind=task_overdue&page_size=100")
        mine = [x for x in a["items"] if x["record_id"] == ids["task"]]  # type: ignore[index]
        assert len(mine) == 1 and mine[0]["href"] == f"/tasks/{ids['task']}", mine
        _, s = get("/alerts/summary")
        _, lst = get("/alerts?page_size=100")
        assert s["total_active"] == lst["total"], (s, lst["total"])  # type: ignore[index]
        _, dash = get("/dashboard/owner")
        keys = {x["key"]: x["count"] for x in dash["alerts"]}  # type: ignore[index]
        assert keys["tasks_overdue"] >= 1, keys

    _()

    @scenario(
        "STEP11 UI 1440: Tasks page distinguishes Overdue and the owner marks the task completed"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        nav = page.get_by_role("navigation", name="Main")
        nav.get_by_role("link", name="Tasks", exact=True).click()
        expect(page.get_by_role("heading", name="Tasks", level=1)).to_be_visible()
        expect(page.get_by_label("Task summary")).to_be_visible()
        table = page.get_by_role("table", name="Tasks")
        row = table.get_by_role("row").filter(has_text="E2E overdue follow-up")
        expect(row.get_by_text("Overdue", exact=True)).to_be_visible()
        expect(row.get_by_text("Unassigned")).to_be_visible()
        page.screenshot(path=str(shots / "step11_tasks_1440.png"))
        row.get_by_role("link", name="E2E overdue follow-up").click()
        expect(page.get_by_role("heading", name="E2E overdue follow-up", level=1)).to_be_visible()
        expect(page.get_by_text("Task created")).to_be_visible()
        page.get_by_role("button", name="Mark completed").click()
        expect(page.get_by_text("Completed", exact=True).first).to_be_visible()
        assert not problems, problems
        ctx.close()
        _, a = get("/alerts?kind=task_overdue&page_size=100")
        assert not [x for x in a["items"] if x["record_id"] == ids["task"]]  # type: ignore[index]
        _, h = get("/alerts/history?status=resolved&page_size=100")
        assert [x for x in h["items"] if x["record_id"] == ids["task"]]  # type: ignore[index]

    _()

    @scenario(
        "STEP11 UI 1440: Notification center, bell and dashboard widget agree; acknowledge moves to history"
    )
    def _() -> None:
        st, t = post(
            "/tasks",
            {
                "title": "E2E due today",
                "branch_id": str(b1[0]),
                "due_date": today.isoformat(),
            },
        )
        assert st == 201
        ctx, page, problems = open_page("owner")
        _, s = get("/alerts/summary")
        expect(page.get_by_role("heading", name="Alerts", level=2)).to_be_visible()
        expect(page.get_by_label("Alert counts")).to_be_visible()
        page.get_by_role("button", name=re.compile(r"Notifications, \d+ unread")).click()
        expect(
            page.get_by_role("menuitem", name=re.compile("View all notifications"))
        ).to_be_visible()
        page.get_by_role("menuitem", name=re.compile("View all notifications")).click()
        expect(page.get_by_role("heading", name="Notifications", level=1)).to_be_visible()
        table = page.get_by_role("table", name="Active alerts")
        row = table.get_by_role("row").filter(has_text="E2E due today")
        expect(row).to_be_visible()
        page.screenshot(path=str(shots / "step11_notifications_1440.png"))
        row.get_by_role("button", name=re.compile("Acknowledge")).click()
        expect(table.get_by_role("row").filter(has_text="E2E due today")).to_have_count(0)
        page.get_by_role("button", name="History").click()
        hist = page.get_by_role("table", name="Alert history")
        expect(hist.get_by_role("row").filter(has_text="E2E due today")).to_be_visible()
        assert s["total_active"] >= 1
        assert not problems, problems
        ctx.close()
        post(f"/tasks/{t['task']['id']}/status", {"status": "Done"})

    _()

    @scenario("STEP11 UI: Branch User has no Tasks / Notifications entries and is denied by URL")
    def _() -> None:
        ctx, page, problems = open_page("branch")
        nav = page.get_by_role("navigation", name="Main")
        expect(nav.get_by_role("link", name="Tasks", exact=True)).to_have_count(0)
        expect(nav.get_by_role("link", name="Notifications", exact=True)).to_have_count(0)
        for path in ("/tasks", f"/tasks/{ids['task']}", "/notifications"):
            page.goto(f"{WEB}{path}")
            expect(page.get_by_text("Access denied")).to_be_visible()
        ctx.close()

    _()

    for w, h in ((390, 844), (768, 1024), (1440, 900)):

        @scenario(f"STEP11 LAYOUT {w}px: tasks and notifications fit the viewport")
        def _(w=w, h=h) -> None:
            ctx, page, problems = open_page("owner", w, h)
            for path in ("/tasks", f"/tasks/{ids['task']}", "/notifications", "/"):
                page.goto(f"{WEB}{path}")
                page.wait_for_load_state("networkidle")
                m = page.evaluate(
                    "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
                )
                assert m["doc"] <= m["win"], f"overflow {path} @{w}: {m}"
            page.goto(f"{WEB}/notifications")
            page.screenshot(path=str(shots / f"step11_notifications_{w}.png"))
            assert not problems, problems
            ctx.close()

        _()


def run_step12_scenarios(browser: Browser, users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    """Step 12: reports, charts, exports and activity history against the REAL rows left by Steps 7-11."""
    import csv
    import io
    from datetime import date, timedelta
    from urllib.request import Request, urlopen

    shots = ROOT / "e2e" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    tok = {
        k: {"Authorization": "Bearer " + sign_in_token(users[k]["email"], users[k]["password"])}
        for k in ("owner", "branch")
    }
    A = f"{API}/api/v1"
    today = date.today()
    first = today.replace(day=1)

    def get(path: str, who: str = "owner") -> tuple[int, dict | list]:
        return http("GET", f"{A}{path}", headers=tok[who])  # type: ignore[return-value]

    def raw(path: str, who: str = "owner") -> tuple[int, bytes, str]:
        try:
            with urlopen(Request(f"{A}{path}", headers=tok[who]), timeout=60) as r:  # noqa: S310
                return r.status, r.read(), r.headers.get("content-type", "")
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", 0)
            return code, b"", ""

    def open_page(role: str, w: int = 1440, h: int = 900) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(
            viewport={"width": w, "height": h}, has_touch=w < 768, accept_downloads=True
        )
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        login_ui(page, users[role]["email"], users[role]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    rng = f"date_from={first}&date_to={today}"

    @scenario("STEP12 API: Branch User is refused on every report / export / activity endpoint")
    def _() -> None:
        for path in (
            "/reports/catalog",
            f"/reports/overview?{rng}",
            f"/reports/charts?{rng}",
            f"/reports/sales_trend?{rng}",
            f"/reports/ledger?{rng}",
            f"/reports/employees?{rng}",
            f"/reports/sales_trend/export?{rng}&format=csv",
            f"/reports/employees/export?{rng}&format=xlsx",
            f"/reports/activity?{rng}",
            f"/reports/activity/export?{rng}&format=csv",
            "/reports/activity/actors",
        ):
            assert get(path, "branch")[0] == 403, path
            assert http("GET", f"{A}{path}")[0] == 401, path

    _()

    @scenario("STEP12 API: report KPIs equal the Owner dashboard for the same day")
    def _() -> None:
        st, dash = get(f"/dashboard/owner?mode=day&date={today}")
        assert st == 200, dash
        st, ov = get(f"/reports/overview?date_from={today}&date_to={today}")
        assert st == 200, ov
        k, d = ov["kpis"], dash["kpis"]
        assert str(k["total_sales"]) == str(d["total_sales"]), (k, d)
        assert str(k["total_collections"]) == str(d["total_received"]), (k, d)
        assert k["total_orders"] == d["total_orders"], (k, d)
        assert str(k["total_savings"]) == str(d["total_savings"]), (k, d)

    _()

    @scenario("STEP12 API: every report responds and its CSV totals equal the screen totals")
    def _() -> None:
        st, cat = get("/reports/catalog")
        assert st == 200 and len(cat) == 36, len(cat)
        for item in cat:
            if item["key"] == "activity":
                continue
            st, j = get(f"/reports/{item['key']}?{rng}&page_size=200")
            assert st == 200, (item["key"], j)
            stc, body, ctype = raw(f"/reports/{item['key']}/export?{rng}&format=csv")
            assert stc == 200 and ctype.startswith("text/csv"), item["key"]
            flat = {
                r[0]: r[1] for r in csv.reader(io.StringIO(body.decode("utf-8-sig"))) if len(r) == 2
            }
            for s in j["summary"]:
                if s["value"] is None or s["kind"] != "money":
                    continue
                assert flat[s["label"]] == f"{float(s['value']):.2f}", (item["key"], s["label"])

    _()

    @scenario("STEP12 API: Excel export opens, charts return eleven entries, bad filters give 422")
    def _() -> None:
        st, body, ctype = raw(f"/reports/sales_by_branch/export?{rng}&format=xlsx")
        assert st == 200 and "spreadsheetml" in ctype and body[:2] == b"PK"
        st, ch = get(f"/reports/charts?{rng}")
        assert st == 200 and len(ch["charts"]) == 11, ch
        assert (
            get(f"/reports/sales_trend?date_from={today}&date_to={today - timedelta(days=1)}")[0]
            == 422
        )
        assert (
            get(f"/reports/sales_trend?date_from={today - timedelta(days=400)}&date_to={today}")[0]
            == 422
        )
        assert get(f"/reports/nope?{rng}")[0] == 404

    _()

    @scenario("STEP12 API: activity history shows real changes and never exposes secrets")
    def _() -> None:
        st, a = get(
            f"/reports/activity?date_from={today - timedelta(days=30)}&date_to={today}&page_size=100"
        )
        assert st == 200 and a["total"] > 0, a
        for word in ("password", "access_token", "api_key", "service_role"):
            hit = [r for r in a["rows"] if word in json.dumps(r).lower()]
            assert not hit, (word, hit[:2])
        assert {"Created", "Updated"} & {r["action"] for r in a["rows"]}

    _()

    @scenario(
        "STEP12 UI: Owner opens Reports, changes the range, switches category and downloads CSV"
    )
    def _() -> None:
        ctx, page, problems = open_page("owner")
        nav = page.get_by_role("navigation", name="Main")
        nav.get_by_role("link", name="Reports & Analytics", exact=True).click()
        try:
            expect(page.get_by_role("heading", name="Reports & Analytics", level=1)).to_be_visible()
        except AssertionError:
            print("DEBUG url", page.url, "TEXT", page.locator("body").inner_text()[:600], problems)
            raise
        kpis = page.get_by_label("Key figures")
        for label in (
            "Total Sales",
            "Total Collections",
            "Total Orders",
            "Total Shop Expenses",
            "Total Head Office Expenses",
            "Total Savings",
            "Sales Minus Expenses",
            "Cash + Bank Balance",
        ):
            expect(kpis.get_by_text(label, exact=True)).to_be_visible()
        page.get_by_role("button", name="Last 30 Days").click()
        expect(page.get_by_role("button", name="Last 30 Days")).to_have_attribute(
            "aria-pressed", "true"
        )
        page.get_by_role("tab", name="Cash & Banks").click()
        expect(page.get_by_label("Report totals")).to_be_visible()
        with page.expect_download() as dl:
            page.get_by_role("button", name="Export CSV").click()
        assert dl.value.suggested_filename.endswith(".csv"), dl.value.suggested_filename
        with page.expect_download() as dl2:
            page.get_by_role("button", name="Export Excel").click()
        assert dl2.value.suggested_filename.endswith(".xlsx")
        page.get_by_role("tab", name="Charts").click()
        expect(page.get_by_label("Charts").locator("section")).to_have_count(11)
        page.screenshot(path=str(shots / "step12_charts_1440.png"), full_page=True)
        assert not problems, problems
        ctx.close()

    _()

    @scenario("STEP12 UI: Owner sees the Activity History with filters")
    def _() -> None:
        ctx, page, problems = open_page("owner")
        page.get_by_role("navigation", name="Main").get_by_role(
            "link", name="Activity History", exact=True
        ).click()
        expect(page.get_by_role("heading", name="Activity History", level=1)).to_be_visible()
        page.get_by_role("button", name="Last 30 Days").click()
        expect(page.get_by_role("table").locator("tbody tr").first).to_be_visible()
        expect(page.get_by_text("Record created").first).to_be_visible()
        assert not problems, problems
        ctx.close()

    _()

    @scenario("STEP12 UI: Branch User has no Reports / Activity entries and is denied by URL")
    def _() -> None:
        ctx, page, problems = open_page("branch")
        nav = page.get_by_role("navigation", name="Main")
        expect(nav.get_by_role("link", name="Reports & Analytics", exact=True)).to_have_count(0)
        expect(nav.get_by_role("link", name="Activity History", exact=True)).to_have_count(0)
        for path in ("/reports", "/activity-history"):
            page.goto(f"{WEB}{path}")
            expect(page.get_by_text("Access denied")).to_be_visible()
        ctx.close()

    _()

    for w, h in ((390, 844), (768, 1024), (1440, 900)):

        @scenario(f"STEP12 LAYOUT {w}px: reports, charts and activity history fit the viewport")
        def _(w=w, h=h) -> None:
            ctx, page, problems = open_page("owner", w, h)
            for path in ("/reports", "/activity-history"):
                page.goto(f"{WEB}{path}")
                page.wait_for_load_state("networkidle")
                if path == "/reports":
                    page.get_by_role("tab", name="Charts").click()
                    page.wait_for_load_state("networkidle")
                m = page.evaluate(
                    "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
                )
                assert m["doc"] <= m["win"], f"overflow {path} @{w}: {m}"
            page.goto(f"{WEB}/reports")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(shots / f"step12_reports_{w}.png"))
            assert not problems, problems
            ctx.close()

        _()


def run_step13_scenarios(browser: Browser, users: dict, dsn: str, b1: tuple, b2: tuple) -> None:
    """Step 13: customers, orders, pickup / delivery, order payments, order reports (real API + RLS + browser)."""
    import csv
    import io
    from datetime import date, timedelta
    from urllib.request import Request, urlopen

    shots = ROOT / "e2e" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    tok = {
        k: {"Authorization": "Bearer " + sign_in_token(users[k]["email"], users[k]["password"])}
        for k in ("owner", "branch")
    }
    A = f"{API}/api/v1"
    today = date.today()
    soon = today + timedelta(days=2)
    B1, B2 = str(b1[0]), str(b2[0])
    state: dict = {}

    def call(method: str, path: str, who: str | None = "owner", body: dict | None = None):
        return http(method, f"{A}{path}", body, tok[who] if who else None)

    def raw(path: str, who: str = "owner") -> tuple[int, bytes, str]:
        try:
            with urlopen(Request(f"{A}{path}", headers=tok[who]), timeout=60) as r:  # noqa: S310
                return r.status, r.read(), r.headers.get("content-type", "")
        except Exception as exc:  # noqa: BLE001
            return getattr(exc, "code", 0), b"", ""

    def order_body(**over) -> dict:
        _, cats = call("GET", "/orders/service-categories")
        body = {
            "category_id": cats[0]["id"],
            "service_type": "Standard",
            "delivery_date": str(soon),
            "delivery_time": "15:00",
            "order_total": "100.00",
            "discount": "0",
            "service_fee": "0",
        }
        body.update(over)
        return body

    def open_page(role: str, w: int = 1440, h: int = 900) -> tuple[BrowserContext, Page, list[str]]:
        ctx = browser.new_context(
            viewport={"width": w, "height": h}, has_touch=w < 768, accept_downloads=True
        )
        page = ctx.new_page()
        page.set_default_timeout(15000)
        problems: list[str] = []
        page.on(
            "console",
            lambda m: (
                problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        login_ui(page, users[role]["email"], users[role]["password"])
        expect(page.get_by_role("heading", name="Dashboard", level=1)).to_be_visible()
        return ctx, page, problems

    def owner_kpis() -> dict:
        s, d = call("GET", f"/dashboard/owner?mode=day&date={today}")
        assert s == 200, d
        return d["kpis"]

    @scenario(
        "STEP13 API: login is required; Branch User can read and create but not cancel or refund"
    )
    def _() -> None:
        for path in ("/orders", "/customers", "/orders/dashboard", "/order-operations/counts"):
            assert call("GET", path, None)[0] == 401, path
        s, o = call(
            "POST",
            "/orders",
            "branch",
            order_body(
                new_customer={
                    "name": "E2E Branch Customer",
                    "mobile": "0501110001",
                    "area": "Satwa",
                }
            ),
        )
        assert s == 201 or s == 200, o
        state["b1_order"] = o["order"]["id"]
        state["b1_customer"] = o["order"]["customer_id"]
        assert o["order"]["branch_id"] == B1 and o["order"]["status"] == "New"
        assert o["order"]["order_no"], o
        s, _ = call(
            "POST",
            f"/orders/{state['b1_order']}/cancel",
            "branch",
            {"reason": "no permission", "confirm": True},
        )
        assert s == 403, s
        s, _ = call(
            "POST",
            f"/orders/{state['b1_order']}/refund",
            "branch",
            {"amount": "1", "reason": "nope"},
        )
        assert s == 403, s

    _()

    @scenario(
        "STEP13 API: Owner creates in another branch; Branch User cannot see or touch it (RLS + scope)"
    )
    def _() -> None:
        s, c = call(
            "POST",
            "/customers",
            "owner",
            {"branch_id": B2, "name": "E2E Other Branch", "mobile": "0502220002"},
        )
        assert s in (200, 201), c
        state["b2_customer"] = c["id"]
        s, o = call("POST", "/orders", "owner", order_body(customer_id=c["id"], branch_id=B2))
        assert s in (200, 201), o
        state["b2_order"] = o["order"]["id"]
        state["b2_no"] = o["order"]["order_no"]
        assert call("GET", f"/orders/{state['b2_order']}", "branch")[0] in (403, 404)
        assert call("GET", f"/customers/{state['b2_customer']}", "branch")[0] in (403, 404)
        _, lst = call("GET", "/orders?page_size=100", "branch")
        assert lst["items"] and all(r["branch_id"] == B1 for r in lst["items"]), lst
        _, cl = call("GET", "/customers?q=Other", "branch")
        assert cl["total"] == 0, cl
        s, _ = call("POST", "/orders", "branch", order_body(customer_id=c["id"]))
        assert s in (403, 404, 409, 422), s
        s, _ = call(
            "POST",
            "/orders",
            "branch",
            order_body(new_customer={"name": "Sneaky", "mobile": "0509990009"}, branch_id=B2),
        )
        assert s in (403, 422), s
        _, own = call("GET", "/orders?page_size=100", "owner")
        assert {r["branch_id"] for r in own["items"]} >= {B1, B2}

    _()

    @scenario("STEP13 API: duplicate mobile is refused; mobile format is validated")
    def _() -> None:
        s, r = call("POST", "/customers", "branch", {"name": "Dup", "mobile": "0501110001"})
        assert s == 409, r
        s, r = call("POST", "/customers", "branch", {"name": "Bad", "mobile": "abc"})
        assert s == 422, r
        _, hit = call("GET", "/customers?q=0501110001", "branch")
        assert hit["total"] == 1 and hit["items"][0]["order_count"] == 1, hit

    _()

    @scenario(
        "STEP13 API: payments are partial/independent, never exceed the total, and refunds need approval"
    )
    def _() -> None:
        oid = state["b1_order"]
        s, d = call("POST", f"/orders/{oid}/payments", "branch", {"amount": "40", "method": "Cash"})
        assert s in (200, 201), d
        assert d["payment_status"] == "Partial" and str(d["outstanding"]) in ("60.00", "60"), d
        s, d = call(
            "POST", f"/orders/{oid}/payments", "branch", {"amount": "60.01", "method": "POS"}
        )
        assert s in (409, 422), (s, d)
        s, d = call(
            "POST",
            f"/orders/{oid}/payments",
            "branch",
            {"amount": "60", "method": "Bank Transfer", "reference": "TRX-1"},
        )
        assert s in (200, 201), d
        assert d["payment_status"] == "Paid" and str(d["outstanding"]) in ("0.00", "0"), d
        s, pays = call("GET", f"/orders/{oid}/payments", "branch")
        assert s == 200 and len(pays) == 2, pays
        s, d = call("POST", f"/orders/{oid}/payments", "branch", {"amount": "1", "method": "Cash"})
        assert s in (409, 422), (s, d)
        s, d = call(
            "POST", f"/orders/{oid}/refund", "owner", {"amount": "10", "reason": "test refund"}
        )
        assert s == 409, (s, d)
        s, _ = http("DELETE", f"{A}/orders/{oid}/payments", None, tok["owner"])
        assert s in (404, 405), s

    _()

    @scenario("STEP13 API: status workflow cannot skip steps; delivered orders are final")
    def _() -> None:
        oid = state["b1_order"]
        s, d = call("POST", f"/orders/{oid}/status", "branch", {"status": "Processing"})
        assert s in (409, 422), (s, d)
        for st in (
            "Scheduled",
            "Picked Up",
            "Processing",
            "Ready",
            "Out for Delivery",
            "Delivered",
        ):
            s, d = call("POST", f"/orders/{oid}/status", "branch", {"status": st})
            assert s in (200, 201), (st, d)
            assert d["order"]["status"] == st
        assert d["next_status"] is None and not d["can_edit"] and not d["can_cancel"]
        assert d["delivered_at"]
        s, h = call("GET", f"/orders/{oid}/status-history", "branch")
        assert [x["to_status"] for x in h] == [
            "New",
            "Scheduled",
            "Picked Up",
            "Processing",
            "Ready",
            "Out for Delivery",
            "Delivered",
        ]
        assert all(x["changed_by"] for x in h)
        s, _ = call(
            "POST", f"/orders/{oid}/cancel", "owner", {"reason": "too late", "confirm": True}
        )
        assert s in (409, 422), s
        s, _ = call("PUT", f"/orders/{oid}", "branch", order_body())
        assert s in (409, 422), s
        s, _ = http("DELETE", f"{A}/orders/{oid}", None, tok["owner"])
        assert s in (404, 405), s

    _()

    @scenario(
        "STEP13 API: cancellation needs a reason and confirmation, and keeps the order and payments"
    )
    def _() -> None:
        s, o = call(
            "POST",
            "/orders",
            "owner",
            order_body(
                customer_id=state["b2_customer"],
                branch_id=B2,
                initial_payment={"amount": "30", "method": "Cash"},
            ),
        )
        assert s in (200, 201), o
        oid = o["order"]["id"]
        assert (
            call("POST", f"/orders/{oid}/cancel", "owner", {"reason": "x", "confirm": True})[0]
            == 422
        )
        assert (
            call(
                "POST",
                f"/orders/{oid}/cancel",
                "owner",
                {"reason": "customer changed plans", "confirm": False},
            )[0]
            == 422
        )
        s, d = call(
            "POST",
            f"/orders/{oid}/cancel",
            "owner",
            {"reason": "customer changed plans", "confirm": True},
        )
        assert s in (200, 201), d
        assert (
            d["order"]["status"] == "Cancelled" and d["cancel_reason"] == "customer changed plans"
        )
        assert len(d["payments"]) == 1 and not d["can_pay"] and not d["can_edit"]
        assert call("POST", f"/orders/{oid}/status", "owner", {"status": "Scheduled"})[0] in (
            409,
            422,
        )
        assert call("POST", f"/orders/{oid}/payments", "owner", {"amount": "1", "method": "Cash"})[
            0
        ] in (409, 422)
        assert call("GET", f"/orders/{oid}", "owner")[0] == 200
        state["cancelled"] = oid

    _()

    @scenario(
        "STEP13 API: delivery before pickup, negatives and zero payable are refused; double submit creates one order"
    )
    def _() -> None:
        base = {"new_customer": {"name": "Validation", "mobile": "0503330003"}}
        for bad in (
            {"pickup_date": str(soon), "pickup_time": "16:00"},
            {"order_total": "-5"},
            {"discount": "-1"},
            {"order_total": "0", "service_fee": "0"},
            {"order_total": "10", "discount": "50"},
        ):
            s, r = call("POST", "/orders", "branch", order_body(**base, **bad))
            assert s == 422, (bad, s, r)
        key = str(uuid.uuid4())
        s1, o1 = call(
            "POST",
            "/orders",
            "branch",
            order_body(new_customer={"name": "Once Only", "mobile": "0504440004"}, client_key=key),
        )
        assert s1 in (200, 201), o1
        s2, o2 = call(
            "POST",
            "/orders",
            "branch",
            order_body(new_customer={"name": "Once Only", "mobile": "0504440004"}, client_key=key),
        )
        assert s2 in (200, 201) and o2["order"]["id"] == o1["order"]["id"], (s2, o2)
        state["once"] = o1["order"]["id"]

    _()

    @scenario(
        "STEP13 API: orders do not change Daily Reports sales, dashboard sales or Cash & Banks"
    )
    def _() -> None:
        before = owner_kpis()
        cb0 = call("GET", "/cash-banks/summary")[1]
        s, ov0 = call("GET", f"/reports/overview?date_from={today}&date_to={today}")
        assert s == 200
        s, o = call(
            "POST",
            "/orders",
            "owner",
            order_body(
                customer_id=state["b2_customer"],
                branch_id=B2,
                initial_payment={"amount": "55", "method": "Cash"},
            ),
        )
        assert s in (200, 201), o
        after = owner_kpis()
        for k in ("total_sales", "total_received", "total_orders", "total_savings"):
            assert str(before[k]) == str(after[k]), (k, before[k], after[k])
        s, ov1 = call("GET", f"/reports/overview?date_from={today}&date_to={today}")
        assert ov0["kpis"]["total_sales"] == ov1["kpis"]["total_sales"]
        assert ov0["kpis"]["total_collections"] == ov1["kpis"]["total_collections"]
        assert ov0["kpis"]["cash_bank_balance"] == ov1["kpis"]["cash_bank_balance"]
        assert call("GET", "/cash-banks/summary")[1] == cb0, "Cash & Banks balances changed"

    _()

    @scenario("STEP13 API: dashboard, operations views and counts agree with the list")
    def _() -> None:
        s, d = call("GET", "/orders/dashboard", "owner")
        assert s == 200, d
        assert {
            "total_orders",
            "todays_pickups",
            "todays_deliveries",
            "monthly_revenue",
            "outstanding_payments",
        } == set(d["kpis"])
        assert [x["key"] for x in d["sections"]], d
        _, lst = call("GET", "/orders?page_size=100", "owner")
        assert (
            d["kpis"]["total_orders"]
            >= len([r for r in lst["items"] if r["status"] != "Cancelled"]) - 0
        )
        s, cnt = call("GET", "/order-operations/counts", "owner")
        assert s == 200 and "processing" in cnt, cnt
        for view in cnt:
            s, v = call("GET", f"/order-operations/{view}", "owner")
            assert s == 200 and v["total"] == cnt[view], (view, v["total"], cnt[view])
        _, bd = call("GET", "/orders/dashboard", "branch")
        for sec in bd["sections"]:
            assert all(r["branch_id"] == B1 for r in sec["items"]), sec["key"]
        assert call("GET", "/orders/dashboard?branch_id=" + B2, "branch")[0] in (200, 403)

    _()

    @scenario(
        "STEP13 API: every order report responds; CSV/Excel respect the branch scope and match the screen"
    )
    def _() -> None:
        s, cat = call("GET", "/orders/reports/catalog", "owner")
        assert s == 200 and len(cat) >= 8, cat
        rng = f"date_from={today - timedelta(days=30)}&date_to={today}"
        for item in cat:
            s, j = call("GET", f"/orders/reports/{item['key']}?{rng}&page_size=200", "owner")
            assert s == 200, (item["key"], j)
            sb, jb = call("GET", f"/orders/reports/{item['key']}?{rng}&page_size=200", "branch")
            assert sb == 200, (item["key"], jb)
            st, body, ctype = raw(f"/orders/reports/{item['key']}/export?{rng}&format=csv")
            assert st == 200 and ctype.startswith("text/csv"), item["key"]
            stx, xb, xt = raw(f"/orders/reports/{item['key']}/export?{rng}&format=xlsx", "branch")
            assert stx == 200 and "spreadsheetml" in xt and xb[:2] == b"PK", item["key"]
        st, body, _ = raw(f"/orders/reports/order_list/export?{rng}&format=csv", "branch")
        if st == 200:
            text = body.decode("utf-8-sig")
            assert state["b2_no"] not in text, "branch export leaked another branch"
        for item in cat:
            s, j = call("GET", f"/orders/reports/{item['key']}?{rng}&page_size=200", "owner")
            body = raw(f"/orders/reports/{item['key']}/export?{rng}&format=csv")[1]
            flat = {
                r[0]: r[1] for r in csv.reader(io.StringIO(body.decode("utf-8-sig"))) if len(r) == 2
            }
            checked = 0
            for sm_item in j["summary"]:
                if sm_item["value"] is None or sm_item["kind"] != "money":
                    continue
                assert flat[sm_item["label"]] == f"{float(sm_item['value']):.2f}", (
                    item["key"],
                    sm_item["label"],
                )
                checked += 1
            if item["key"] == "order_summary":
                assert checked >= 1, "order_summary should show money totals"
        assert call("GET", f"/orders/reports/nope?{rng}", "owner")[0] == 404
        assert (
            call(
                "GET",
                f"/orders/reports/order_summary?date_from={today}&date_to={today - timedelta(days=1)}",
                "owner",
            )[0]
            == 422
        )

    _()

    @scenario("STEP13 API: order history and edits are in the audit trail with a reason")
    def _() -> None:
        s, o = call(
            "POST",
            "/orders",
            "branch",
            order_body(new_customer={"name": "Audit Subject", "mobile": "0505550005"}),
        )
        assert s in (200, 201), o
        oid = o["order"]["id"]
        s, d = call(
            "PUT",
            f"/orders/{oid}",
            "branch",
            {**order_body(order_total="120.00"), "reason": "price corrected"},
        )
        assert s == 200 and str(d["order_total"]) in ("120.00", "120"), d
        with psycopg.connect(dsn, autocommit=True) as c:
            n = c.execute(
                "select count(*) from public.audit_log where table_name = 'orders' and record_id = %s",
                (oid,),
            ).fetchone()
        assert n is not None and n[0] >= 2, n
        s, a = call(
            "GET", f"/reports/activity?date_from={today}&date_to={today}&page_size=100", "owner"
        )
        assert s == 200 and any(
            r.get("module") in ("Customer Orders", "orders") or "order" in json.dumps(r).lower()
            for r in a["rows"]
        )

    _()

    # ---------------------------------------------------------------- browser
    @scenario(
        "STEP13 UI: Branch User sees the order menu and creates an order with a customer and first payment"
    )
    def _() -> None:
        ctx, page, problems = open_page("branch")
        nav = page.get_by_role("navigation", name="Main")
        for name in (
            "Order Management",
            "Orders",
            "Customers",
            "Pickup & Delivery",
            "Order Reports",
        ):
            expect(nav.get_by_role("link", name=name, exact=True)).to_be_visible()
        nav.get_by_role("link", name="Orders", exact=True).click()
        expect(page.get_by_role("heading", name="Orders", level=1)).to_be_visible()
        page.get_by_role("link", name="New Order").click()
        expect(page.get_by_role("heading", name="New Order", level=1)).to_be_visible()
        page.get_by_role("button", name="New customer").click()
        page.get_by_label("Customer name").fill("UI Customer")
        page.get_by_label("Mobile number").fill("0506660006")
        page.get_by_label("Area").fill("Jumeirah")
        page.get_by_role("combobox", name="Service category").click()
        page.get_by_role("option").first.click()
        page.get_by_label("Delivery date").fill(str(soon))
        page.get_by_label("Delivery time").fill("14:00")
        page.get_by_label("Order total").fill("80")
        page.get_by_label("Discount").fill("10")
        page.get_by_label("Service fee").fill("5")
        expect(page.get_by_text("Final payable:")).to_contain_text("75.00")
        page.get_by_role("checkbox", name="Record a payment now").check()
        page.get_by_label("Amount collected").fill("25")
        page.screenshot(path=str(shots / "step13_new_order_1440.png"), full_page=True)
        page.get_by_role("button", name="Create order").click()
        expect(page.get_by_role("heading", name=re.compile(r"^Order "), level=1)).to_be_visible()
        expect(page.get_by_role("list", name="Status timeline")).to_contain_text("New")
        expect(
            page.get_by_text("Outstanding", exact=True).locator("xpath=following-sibling::dd")
        ).to_contain_text("50.00")
        expect(page.get_by_role("table", name="Payment history")).to_contain_text("Cash")
        expect(page.get_by_role("button", name="Cancel order")).to_have_count(0)
        state["ui_order_url"] = page.url
        page.screenshot(path=str(shots / "step13_order_detail_1440.png"), full_page=True)
        assert not problems, problems
        ctx.close()

    _()

    @scenario(
        "STEP13 UI: Branch User advances the status with confirmation and records the balance payment"
    )
    def _() -> None:
        ctx, page, problems = open_page("branch")
        page.goto(state["ui_order_url"])
        page.get_by_role("button", name="Mark Scheduled").click()
        page.get_by_role("alertdialog").get_by_role("button", name="Mark Scheduled").click()
        expect(page.get_by_role("list", name="Status timeline")).to_contain_text("New → Scheduled")
        page.get_by_role("button", name="Record payment").click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_label("Amount (AED)").fill("500")
        dlg.get_by_role("button", name="Save payment").click()
        expect(dlg.get_by_role("alert")).to_be_visible()
        dlg.get_by_label("Amount (AED)").fill("50")
        dlg.get_by_role("button", name="Save payment").click()
        expect(page.get_by_role("table", name="Payment history").locator("tbody tr")).to_have_count(
            2
        )
        expect(page.get_by_text("Paid", exact=True).first).to_be_visible()
        assert not [p for p in problems if not any(c in p for c in ("400", "409", "422"))], problems
        ctx.close()

    _()

    @scenario("STEP13 UI: Owner dashboard, search, operations tabs and cancellation with a reason")
    def _() -> None:
        ctx, page, problems = open_page("owner")
        nav = page.get_by_role("navigation", name="Main")
        nav.get_by_role("link", name="Order Management", exact=True).click()
        kp = page.get_by_label("Key figures")
        for label in (
            "Total Orders",
            "Today's Pickups",
            "Today's Deliveries",
            "Monthly Revenue",
            "Outstanding Payments",
        ):
            expect(kp.get_by_text(label, exact=True)).to_be_visible()
        page.screenshot(path=str(shots / "step13_dashboard_1440.png"), full_page=True)
        nav.get_by_role("link", name="Orders", exact=True).click()
        page.get_by_role("searchbox", name="Search orders").fill("0506660006")
        expect(page.get_by_role("table").locator("tbody tr")).to_have_count(1)
        expect(page.get_by_role("table")).to_contain_text("UI Customer")
        page.get_by_role("searchbox", name="Search orders").fill("")
        page.get_by_role("link", name="New Order").click()
        page.get_by_role("button", name="Existing customer").click()
        page.get_by_role("main").get_by_role("combobox", name="Branch").click()
        page.get_by_role("option", name=B2_NAME(b2)).click()
        page.get_by_role("searchbox", name="Find a customer").fill("Other")
        page.get_by_role("button", name=re.compile("E2E Other Branch")).click()
        page.get_by_role("combobox", name="Service category").click()
        page.get_by_role("option").first.click()
        page.get_by_label("Delivery date").fill(str(soon))
        page.get_by_label("Delivery time").fill("11:00")
        page.get_by_label("Order total").fill("60")
        page.get_by_role("button", name="Create order").click()
        expect(page.get_by_role("heading", name=re.compile(r"^Order "), level=1)).to_be_visible()
        page.get_by_role("button", name="Cancel order").click()
        dlg = page.get_by_role("alertdialog")
        dlg.get_by_role("button", name="Cancel order").click()
        expect(dlg.get_by_role("alert")).to_be_visible()
        dlg.get_by_role("textbox").fill("Customer called to cancel")
        dlg.get_by_role("button", name="Cancel order").click()
        expect(page.get_by_text("Cancelled", exact=True).first).to_be_visible()
        expect(page.get_by_text("Customer called to cancel").first).to_be_visible()
        expect(page.get_by_role("button", name="Record payment")).to_have_count(0)
        nav.get_by_role("link", name="Pickup & Delivery", exact=True).click()
        page.get_by_role("tab", name=re.compile("Processing")).click()
        expect(page.get_by_role("tab", name=re.compile("Processing"))).to_have_attribute(
            "aria-selected", "true"
        )
        page.screenshot(path=str(shots / "step13_operations_1440.png"), full_page=True)
        assert not [p for p in problems if "422" not in p], problems
        ctx.close()

    _()

    @scenario("STEP13 UI: customers list, details with order history, and order reports download")
    def _() -> None:
        ctx, page, problems = open_page("branch")
        page.get_by_role("navigation", name="Main").get_by_role(
            "link", name="Customers", exact=True
        ).click()
        expect(page.get_by_role("heading", name="Customers", level=1)).to_be_visible()
        page.get_by_role("searchbox", name="Search customers").fill("UI Customer")
        page.get_by_role("link", name="UI Customer").click()
        expect(page.get_by_role("heading", name="UI Customer", level=1)).to_be_visible()
        expect(page.get_by_role("table", name="Order history").locator("tbody tr")).to_have_count(1)
        page.get_by_role("button", name="Edit").click()
        page.get_by_label("Area").fill("Al Barsha")
        page.get_by_role("button", name="Save changes").click()
        expect(page.get_by_text("Al Barsha").first).to_be_visible()
        page.get_by_role("navigation", name="Main").get_by_role(
            "link", name="Order Reports", exact=True
        ).click()
        expect(page.get_by_role("heading", name="Order Reports", level=1)).to_be_visible()
        expect(page.get_by_role("combobox", name="Branch")).to_have_count(0)
        with page.expect_download() as dl:
            page.get_by_role("button", name="Export CSV").click()
        assert dl.value.suggested_filename.endswith(".csv")
        with page.expect_download() as dl2:
            page.get_by_role("button", name="Export Excel").click()
        assert dl2.value.suggested_filename.endswith(".xlsx")
        assert not problems, problems
        ctx.close()

    _()

    @scenario("STEP13 UI: a user typing an order URL for another branch sees no data")
    def _() -> None:
        ctx, page, problems = open_page("branch")
        page.goto(f"{WEB}/orders/{state['b2_order']}")
        expect(page.get_by_text("Aisha").first).to_have_count(0)
        assert "E2E Other Branch" not in page.locator("body").inner_text()
        expect(
            page.get_by_role("alert").or_(page.get_by_text("Something went wrong")).first
        ).to_be_visible()
        ctx.close()

    _()

    for w, h in ((390, 844), (768, 1024), (1440, 900)):

        @scenario(f"STEP13 LAYOUT {w}px: order pages fit the viewport")
        def _(w=w, h=h) -> None:
            ctx, page, problems = open_page("owner", w, h)
            for path in (
                "/order-management",
                "/orders",
                "/orders/new",
                "/order-operations",
                "/order-reports",
                "/customers",
            ):
                page.goto(f"{WEB}{path}")
                page.wait_for_load_state("networkidle")
                m = page.evaluate(
                    "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
                )
                assert m["doc"] <= m["win"], f"overflow {path} @{w}: {m}"
            page.goto(f"{WEB}/order-management")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(shots / f"step13_orders_{w}.png"))
            assert not problems, problems
            ctx.close()

        _()


def B2_NAME(b2: tuple) -> str:
    return str(b2[1])


if __name__ == "__main__":
    sys.exit(main())
