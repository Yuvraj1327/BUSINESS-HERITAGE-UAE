#!/usr/bin/env python3
"""Trusted admin tool: create / adopt / deactivate / activate ERP accounts. Run by an operator, never by the app.

There is NO public registration. Accounts exist only because an operator ran this script (or followed the manual
steps in docs/authentication/OWNER_ACCOUNT_SETUP.md).

Environment (read from the process environment ONLY -- never from the app's Settings, never from files in git):
  SUPABASE_URL                  e.g. https://<project-ref>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY     backend/operator secret; bypasses RLS. Never expose it to the browser.
  ADMIN_DATABASE_URL            a privileged Postgres connection (e.g. the `postgres` role) used to write profiles
  PASSWORD_RESET_REDIRECT_URL   (create only) where the invite link lands, e.g. https://erp.example.com/reset-password

Commands
  create     --email E --full-name N --role owner|branch [--branch NAME]
             Creates the Auth user (email pre-confirmed, NO password), inserts the profile, and emails a
             password-set link. If the profile insert fails the Auth user is removed again (no orphans).
  adopt      --user-id UUID --full-name N --role ... [--branch NAME]
             For a user already created in the Supabase dashboard: only inserts the profile.
  deactivate --user-id UUID | --email E     profile.is_active=false and blocks new Auth sign-ins
  activate   --user-id UUID | --email E     reverses deactivate

Passwords are never accepted on the command line, printed, or logged.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from typing import Any

import httpx
import psycopg

UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
BAN_FOREVER = "876000h"  # ~100 years


class ProvisionError(Exception):
    pass


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ProvisionError(f"environment variable {name} is required")
    return value


class AuthAdmin:
    """Minimal Supabase Auth admin API client (service-role)."""

    def __init__(
        self, base_url: str, service_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base = base_url.rstrip("/") + "/auth/v1"
        self.http = httpx.Client(
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=15,
            transport=transport,
        )

    def _check(self, resp: httpx.Response, what: str) -> dict[str, Any]:
        if resp.status_code >= 400:
            try:
                detail = (
                    resp.json().get("msg")
                    or resp.json().get("message")
                    or resp.json().get("error_code")
                )
            except ValueError:
                detail = None
            raise ProvisionError(
                f"{what} failed (HTTP {resp.status_code}){': ' + str(detail) if detail else ''}"
            )
        return resp.json() if resp.content else {}

    def create_user(self, email: str) -> str:
        body = self._check(
            self.http.post(
                f"{self.base}/admin/users", json={"email": email, "email_confirm": True}
            ),
            "creating the Auth user",
        )
        return str(body["id"])

    def find_user_id(self, email: str) -> str:
        body = self._check(
            self.http.get(f"{self.base}/admin/users", params={"per_page": 1000}), "listing users"
        )
        for u in body.get("users", []):
            if str(u.get("email", "")).lower() == email.lower():
                return str(u["id"])
        raise ProvisionError("no Auth user with that email")

    def delete_user(self, user_id: str) -> None:
        self._check(
            self.http.delete(f"{self.base}/admin/users/{user_id}"), "deleting the Auth user"
        )

    def set_ban(self, user_id: str, banned: bool) -> None:
        self._check(
            self.http.put(
                f"{self.base}/admin/users/{user_id}",
                json={"ban_duration": BAN_FOREVER if banned else "none"},
            ),
            "updating the Auth user",
        )

    def send_recovery(self, email: str, redirect_to: str) -> None:
        self._check(
            self.http.post(
                f"{self.base}/recover", params={"redirect_to": redirect_to}, json={"email": email}
            ),
            "sending the password email",
        )


def resolve_branch(conn: psycopg.Connection, name: str) -> uuid.UUID:
    row = conn.execute(
        "select id from public.branches where upper(name) = upper(%s)", (name.strip(),)
    ).fetchone()
    if row is None:
        names = [
            r[0] for r in conn.execute("select name from public.branches order by sort_order, name")
        ]
        raise ProvisionError(f"unknown branch {name!r}. Valid branches: {', '.join(names)}")
    return row[0]


def insert_profile(
    conn: psycopg.Connection, user_id: str, full_name: str, role: str, branch: str | None
) -> None:
    if role == "owner" and branch:
        raise ProvisionError("an owner has no branch (omit --branch)")
    if role == "branch" and not branch:
        raise ProvisionError("a branch user needs --branch")
    if not full_name.strip():
        raise ProvisionError("--full-name must not be blank")
    branch_id = resolve_branch(conn, branch) if branch else None
    with conn.transaction():
        try:
            conn.execute(
                "insert into public.profiles (user_id, full_name, role, branch_id) values (%s, %s, %s, %s)",
                (user_id, full_name.strip(), role, branch_id),
            )
        except psycopg.errors.UniqueViolation:
            raise ProvisionError("that user already has a profile") from None
        except psycopg.errors.ForeignKeyViolation:
            raise ProvisionError(
                "no Auth user with that id exists (create the user in Supabase Auth first)"
            ) from None


def set_active(conn: psycopg.Connection, user_id: str, active: bool) -> None:
    with conn.transaction():
        n = conn.execute(
            "update public.profiles set is_active = %s where user_id = %s", (active, user_id)
        ).rowcount
    if n != 1:
        raise ProvisionError("no profile for that user")


def run(args: argparse.Namespace, *, transport: httpx.BaseTransport | None = None) -> str:
    admin = AuthAdmin(_env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY"), transport)
    with psycopg.connect(
        _env("ADMIN_DATABASE_URL"), autocommit=True, prepare_threshold=None
    ) as conn:
        if args.command == "create":
            redirect = _env("PASSWORD_RESET_REDIRECT_URL")
            user_id = admin.create_user(args.email)
            try:
                insert_profile(conn, user_id, args.full_name, args.role, args.branch)
            except Exception:
                admin.delete_user(user_id)  # compensate: never leave an Auth user without a profile
                raise
            admin.send_recovery(args.email, redirect)
            return f"created {args.role} account {user_id}; password-set email sent to {args.email}"
        if args.command == "adopt":
            _require_uuid(args.user_id)
            insert_profile(conn, args.user_id, args.full_name, args.role, args.branch)
            return f"profile created for {args.user_id}"
        _require_target(args)
        user_id = args.user_id or admin.find_user_id(args.email)
        _require_uuid(user_id)
        active = args.command == "activate"
        if (
            not active
        ):  # block first so a failure leaves the account usable rather than half-deactivated
            set_active(conn, user_id, False)
            admin.set_ban(user_id, True)
        else:
            admin.set_ban(user_id, False)
            set_active(conn, user_id, True)
        return f"{'activated' if active else 'deactivated'} {user_id}"


def _require_uuid(value: str) -> None:
    if not UUID_RE.match(value):
        raise ProvisionError("--user-id must be a UUID")


def _require_target(args: argparse.Namespace) -> None:
    if not (args.user_id or args.email):
        raise ProvisionError("give --user-id or --email")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("create", "adopt"):
        s = sub.add_parser(name)
        if name == "create":
            s.add_argument("--email", required=True)
        else:
            s.add_argument("--user-id", required=True)
        s.add_argument("--full-name", required=True)
        s.add_argument("--role", required=True, choices=["owner", "branch"])
        s.add_argument("--branch")
    for name in ("deactivate", "activate"):
        s = sub.add_parser(name)
        s.add_argument("--user-id")
        s.add_argument("--email")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(run(args))
    except ProvisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
