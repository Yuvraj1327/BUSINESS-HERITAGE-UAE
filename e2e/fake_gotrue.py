#!/usr/bin/env python3
"""SIMULATED Supabase Auth (GoTrue) for local end-to-end tests.  *** NOT real Supabase. ***

It speaks just enough of the GoTrue HTTP API for supabase-js and the ERP backend:
  JWKS (ES256), password sign-in, refresh, PKCE code exchange, logout, recover (mail goes to an in-memory
  outbox), verify link -> redirect with ?code=, update user (password), get user, and the admin user endpoints
  used by backend/scripts/provision_account.py.
Control endpoints (/__control/...) let the test harness read the outbox, seed users and rotate signing keys.
Passwords are stored in memory only. Test data only -- never point real traffic at this.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 54321
BASE = f"http://localhost:{PORT}"
ISS = f"{BASE}/auth/v1"
SERVICE_KEY = "e2e-service-role-key-not-real"
ACCESS_TTL = 3600
DB_DSN = os.environ.get(
    "FAKE_AUTH_DB_DSN"
)  # optional: mirror users into the test database's auth.users


def db_exec(sql: str, params: tuple[Any, ...]) -> None:
    """In real Supabase auth.users IS the Auth user table; the simulation mirrors it so profiles can reference it."""
    if not DB_DSN:
        return
    import psycopg

    with psycopg.connect(DB_DSN, autocommit=True) as c:
        c.execute(sql, params)


class Key:
    def __init__(self) -> None:
        self.kid = "e2e-" + secrets.token_hex(4)
        self.private = ec.generate_private_key(ec.SECP256R1())
        jwk = json.loads(ECAlgorithm(ECAlgorithm.SHA256).to_jwk(self.private.public_key()))
        jwk.update({"kid": self.kid, "alg": "ES256", "use": "sig"})
        self.jwk = jwk


class State:
    key = Key()
    users: dict[str, dict[str, Any]] = {}
    sessions: dict[str, dict[str, Any]] = {}  # refresh_token -> {user_id, session_id}
    codes: dict[str, dict[str, Any]] = {}  # auth code -> {user_id, challenge}
    recovery_tokens: dict[str, dict[str, Any]] = {}
    outbox: list[dict[str, Any]] = []
    banned: set[str] = set()


def b64url_sha256(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def user_json(u: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": u["id"],
        "aud": "authenticated",
        "role": "authenticated",
        "email": u["email"],
        "app_metadata": {},
        "user_metadata": {},
        "created_at": "2026-01-01T00:00:00Z",
    }


def issue_session(
    user_id: str, session_id: str | None = None, refresh: str | None = None
) -> dict[str, Any]:
    u = State.users[user_id]
    now = int(time.time())
    sid = session_id or str(uuid.uuid4())
    claims = {
        "iss": ISS,
        "aud": "authenticated",
        "sub": user_id,
        "role": "authenticated",
        "email": u["email"],
        "session_id": sid,
        "iat": now,
        "exp": now + ACCESS_TTL,
        "aal": "aal1",
        "user_metadata": {},
        "app_metadata": {},
    }
    access = jwt.encode(
        claims, State.key.private, algorithm="ES256", headers={"kid": State.key.kid}
    )
    new_refresh = secrets.token_urlsafe(24)
    if refresh:
        State.sessions.pop(refresh, None)
    State.sessions[new_refresh] = {"user_id": user_id, "session_id": sid}
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": ACCESS_TTL,
        "expires_at": now + ACCESS_TTL,
        "refresh_token": new_refresh,
        "user": user_json(u),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "FakeGoTrue/0"

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet
        pass

    # ---- plumbing
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header(
            "Access-Control-Allow-Headers",
            "authorization, apikey, content-type, x-client-info, x-supabase-api-version",
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    def _json(self, status: int, body: Any) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _err(self, status: int, code: str, msg: str) -> None:
        self._json(status, {"code": status, "error_code": code, "msg": msg})

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _bearer_user(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            payload = jwt.decode(
                auth[7:],
                State.key.private.public_key(),
                algorithms=["ES256"],
                audience="authenticated",
                issuer=ISS,
            )
        except jwt.PyJWTError:
            return None
        return str(payload["sub"])

    def _is_admin(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {SERVICE_KEY}"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ---- routes
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/auth/v1/.well-known/jwks.json":
            return self._json(200, {"keys": [State.key.jwk]})
        if url.path == "/auth/v1/user":
            uid = self._bearer_user()
            return (
                self._json(200, user_json(State.users[uid]))
                if uid in State.users
                else self._err(401, "bad_jwt", "invalid JWT")
            )
        if url.path == "/auth/v1/verify":
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            rec = State.recovery_tokens.pop(q.get("token", ""), None)
            if rec is None:
                loc = f"{q.get('redirect_to', '')}#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired"
            else:
                code = secrets.token_urlsafe(16)
                State.codes[code] = {"user_id": rec["user_id"], "challenge": rec["challenge"]}
                loc = f"{q['redirect_to']}?code={code}"
            self.send_response(302)
            self.send_header("Location", loc)
            self.end_headers()
            return
        if url.path == "/auth/v1/admin/users":
            return (
                self._json(200, {"users": [user_json(u) for u in State.users.values()]})
                if self._is_admin()
                else self._err(401, "no_authorization", "service role required")
            )
        if url.path == "/__control/outbox":
            return self._json(200, State.outbox)
        self._err(404, "not_found", "no such route")

    def do_POST(self) -> None:
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        body = self._body()
        if url.path == "/auth/v1/token":
            grant = q.get("grant_type")
            if grant == "password":
                u = next(
                    (
                        x
                        for x in State.users.values()
                        if x["email"].lower() == str(body.get("email", "")).lower()
                    ),
                    None,
                )
                if u is None or u["password"] != body.get("password"):
                    return self._err(400, "invalid_credentials", "Invalid login credentials")
                if u["id"] in State.banned:
                    return self._err(400, "user_banned", "User is banned")
                return self._json(200, issue_session(u["id"]))
            if grant == "refresh_token":
                s = State.sessions.get(str(body.get("refresh_token")))
                if s is None or s["user_id"] in State.banned:
                    return self._err(400, "refresh_token_not_found", "Invalid Refresh Token")
                return self._json(
                    200, issue_session(s["user_id"], s["session_id"], str(body["refresh_token"]))
                )
            if grant == "pkce":
                c = State.codes.pop(str(body.get("auth_code")), None)
                if c is None or b64url_sha256(str(body.get("code_verifier", ""))) != c["challenge"]:
                    return self._err(400, "flow_state_not_found", "invalid flow state")
                return self._json(200, issue_session(c["user_id"]))
            return self._err(400, "unsupported_grant_type", "unsupported")
        if url.path == "/auth/v1/logout":
            uid = self._bearer_user()
            for rt in [k for k, v in State.sessions.items() if v["user_id"] == uid]:
                State.sessions.pop(rt)
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        if url.path == "/auth/v1/recover":
            email = str(body.get("email", ""))
            u = next((x for x in State.users.values() if x["email"].lower() == email.lower()), None)
            if u:  # unknown emails get the same 200 (GoTrue does not reveal existence)
                token = secrets.token_urlsafe(16)
                State.recovery_tokens[token] = {
                    "user_id": u["id"],
                    "challenge": body.get("code_challenge", ""),
                }
                redirect = q.get("redirect_to", "")
                State.outbox.append(
                    {
                        "to": email,
                        "link": f"{ISS}/verify?token={token}&type=recovery&redirect_to={redirect}",
                    }
                )
            return self._json(200, {})
        if url.path == "/auth/v1/admin/users":
            if not self._is_admin():
                return self._err(401, "no_authorization", "service role required")
            uid = str(uuid.uuid4())
            State.users[uid] = {
                "id": uid,
                "email": body["email"],
                "password": secrets.token_hex(16),
            }
            db_exec("insert into auth.users (id, email) values (%s, %s)", (uid, body["email"]))
            return self._json(200, user_json(State.users[uid]))
        if url.path == "/__control/seed":  # test-data only: create a user with a known password
            uid = body.get("id") or str(uuid.uuid4())
            State.users[uid] = {"id": uid, "email": body["email"], "password": body["password"]}
            db_exec("insert into auth.users (id, email) values (%s, %s)", (uid, body["email"]))
            return self._json(200, {"id": uid})
        if url.path == "/__control/rotate_keys":
            State.key = Key()
            return self._json(200, {"kid": State.key.kid})
        self._err(404, "not_found", "no such route")

    def do_PUT(self) -> None:
        url = urlparse(self.path)
        body = self._body()
        if url.path == "/auth/v1/user":
            uid = self._bearer_user()
            if uid not in State.users:
                return self._err(401, "bad_jwt", "invalid JWT")
            if body.get("password") == State.users[uid]["password"]:
                return self._err(
                    422, "same_password", "New password should be different from the old password."
                )
            State.users[uid]["password"] = body["password"]
            return self._json(200, user_json(State.users[uid]))
        if url.path.startswith("/auth/v1/admin/users/") and self._is_admin():
            uid = url.path.rsplit("/", 1)[1]
            if body.get("ban_duration") == "none":
                State.banned.discard(uid)
            elif body.get("ban_duration"):
                State.banned.add(uid)
            return self._json(200, user_json(State.users[uid]))
        self._err(404, "not_found", "no such route")

    def do_DELETE(self) -> None:
        url = urlparse(self.path)
        if url.path.startswith("/auth/v1/admin/users/") and self._is_admin():
            uid = url.path.rsplit("/", 1)[1]
            State.users.pop(uid, None)
            db_exec("delete from auth.users where id = %s", (uid,))
            return self._json(200, {})
        self._err(404, "not_found", "no such route")


if __name__ == "__main__":
    print(f"fake GoTrue (SIMULATED, not Supabase) on {BASE}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
