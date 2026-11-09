"""Database test harness (Step 2).

Runs against a REAL PostgreSQL server (RLS cannot be tested with SQLite or mocks).
Set TEST_PG_ADMIN_DSN to a superuser connection on a DISPOSABLE server, e.g.
    host=/tmp port=54329 user=postgres dbname=postgres
Each session creates a brand-new database, applies tests/stub_supabase.sql (stand-in for the Supabase-managed
auth schema and roles) and then every migration in order. The database is dropped afterwards.
It never touches any existing database.
"""
import contextlib
import json
import os
import pathlib
import uuid

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "migrations").glob("*.sql"))
STUB = ROOT / "tests" / "stub_supabase.sql"
ADMIN_DSN = os.environ.get("TEST_PG_ADMIN_DSN", "host=/tmp port=54329 user=postgres dbname=postgres")


def _dsn_for(dbname: str) -> str:
    return ADMIN_DSN.replace("dbname=postgres", f"dbname={dbname}")


@pytest.fixture(scope="session")
def dsn():
    name = f"alsafa_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    target = _dsn_for(name)
    try:
        with psycopg.connect(target, autocommit=True) as c:
            c.execute(STUB.read_text())
            for m in MIGRATIONS:
                c.execute(m.read_text())
        yield target
    finally:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture()
def conn(dsn):
    """Superuser connection inside a transaction that is rolled back after each test."""
    c = psycopg.connect(dsn)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def q(conn, sql, params=None):
    return conn.execute(sql, params).fetchall()


def one(conn, sql, params=None):
    return conn.execute(sql, params).fetchone()[0]


@contextlib.contextmanager
def as_user(conn, uid):
    """Act as an authenticated Supabase user (role + JWT claims), like the backend does per request."""
    with conn.transaction():
        conn.execute("set local role authenticated")
        conn.execute("select set_config('request.jwt.claims', %s, true)",
                     [json.dumps({"sub": str(uid), "role": "authenticated"})])
        yield
        conn.execute("reset role")
        conn.execute("select set_config('request.jwt.claims', '', true)")


@contextlib.contextmanager
def as_anon(conn):
    with conn.transaction():
        conn.execute("set local role anon")
        yield
        conn.execute("reset role")


class World:
    """Test users and branch ids. Created as superuser inside the test transaction."""
    def __init__(self, conn):
        self.conn = conn
        self.branch = {r[1]: r[0] for r in q(conn, "select id, name from public.branches")}
        self.owner = self.make_user("owner", None, "Owner One")
        self.main = self.make_user("branch", "ALSAFA MAIN", "Main Manager")
        self.jernas = self.make_user("branch", "JERNAS", "Jernas Manager")

    def make_user(self, role, branch_name, full_name):
        uid = one(self.conn, "insert into auth.users (email) values (%s) returning id",
                  [f"{uuid.uuid4().hex[:8]}@example.test"])
        bid = self.branch[branch_name] if branch_name else None
        self.conn.execute("insert into public.profiles (user_id, full_name, role, branch_id) values (%s,%s,%s,%s)",
                          [uid, full_name, role, bid])
        return uid

    def category(self, name="Utilities"):
        return one(self.conn, "select id from public.expense_categories where name = %s", [name])


@pytest.fixture()
def w(conn):
    return World(conn)


def add_report(conn, branch_id, d, sales, cash=0, pos=0, tr=0, link=0, exp=0, sav=0, orders=1):
    return one(conn, """insert into public.daily_reports
        (report_date, branch_id, total_sales, order_count, cash_received, pos_amount, bank_transfer,
         link_payment, shop_expenses, shop_savings) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        [d, branch_id, sales, orders, cash, pos, tr, link, exp, sav])
