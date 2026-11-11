"""Step 5 database-level RBAC verification (real PostgreSQL, real migrations 0001-0010, real RLS)."""
import json
import uuid

import psycopg
import pytest
from psycopg import errors as E

from conftest import add_report, as_anon, as_user, one, q

OWNER_ONLY_TABLES = ["opening_balances", "opening_branch_cash", "suppliers", "head_office_expenses", "employees",
                     "tasks", "trade_licenses", "rental_agreements", "pdc_cheques"]


def seed_private_rows(conn, w):
    """One row in each owner-only table we can create cheaply, inserted as superuser."""
    conn.execute("insert into public.suppliers (name, amount_owed) values ('Secret Supplier', 500)")
    conn.execute("insert into public.employees (full_name, branch_id, monthly_salary) values ('Secret Employee', %s, 9999)",
                 [w.branch["JERNAS"]])
    conn.execute("insert into public.tasks (title) values ('Secret task')")


# ------------------------------------------------------------------ structural: every table has RLS + no anon policy
class TestStructure:
    def test_rls_enabled_everywhere(self, conn):
        bad = q(conn, """select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
                         where n.nspname='public' and c.relkind='r' and not c.relrowsecurity""")
        assert bad == []

    def test_no_policy_targets_anon_or_public(self, conn):
        rows = q(conn, "select tablename, policyname, roles from pg_policies where schemaname='public'")
        assert rows
        for table, name, roles in rows:
            assert "anon" not in roles and "public" not in roles, (table, name, roles)

    def test_owner_only_tables_have_only_owner_policies(self, conn):
        for t in OWNER_ONLY_TABLES:
            rows = q(conn, "select policyname, qual, with_check from pg_policies where schemaname='public' and tablename=%s", [t])
            assert rows, t
            for name, qual, check in rows:
                assert "is_owner()" in f"{qual} {check}", (t, name)

    def test_anon_has_no_table_privileges(self, conn):
        assert q(conn, """select table_name, privilege_type from information_schema.role_table_grants
                          where grantee='anon' and table_schema='public'""") == []

    def test_no_delete_or_update_grants_on_daily_reports(self, conn):
        privs = {r[0] for r in q(conn, """select privilege_type from information_schema.role_table_grants
                                          where grantee='authenticated' and table_name='daily_reports'""")}
        assert privs == {"SELECT", "INSERT"}

    def test_audit_log_has_no_write_grants_for_users(self, conn):
        privs = {r[0] for r in q(conn, """select privilege_type from information_schema.role_table_grants
                                          where grantee='authenticated' and table_name='audit_log'""")}
        assert privs == {"SELECT"}

    def test_security_definer_helpers_pin_search_path(self, conn):
        rows = q(conn, """select p.proname, p.proconfig from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                          where n.nspname='app' and p.prosecdef""")
        assert rows
        for name, cfg in rows:
            assert cfg and any(c.startswith("search_path=") for c in cfg), name

    def test_helpers_not_executable_by_anon(self, conn):
        for fn in ("app.user_role()", "app.is_owner()", "app.branch_id()", "app.can_access_branch(uuid)",
                   "app.log_access_denied(text,text,jsonb)"):
            assert one(conn, "select has_function_privilege('anon', %s, 'execute')", [fn]) is False, fn


# ------------------------------------------------------------------ branch user: owner-only data is invisible
class TestBranchUserDenied:
    def test_cannot_read_owner_only_tables(self, conn, w):
        seed_private_rows(conn, w)
        for uid in (w.main, w.jernas):
            with as_user(conn, uid):
                for t in OWNER_ONLY_TABLES:
                    assert one(conn, f"select count(*) from public.{t}") == 0, t

    def test_cannot_insert_into_owner_only_tables(self, conn, w):
        stmts = ["insert into public.suppliers (name) values ('x')",
                 "insert into public.tasks (title) values ('x')",
                 f"insert into public.employees (full_name, branch_id) values ('x','{w.branch['ALSAFA MAIN']}')"]
        for s in stmts:
            with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
                conn.execute(s)

    def test_cannot_update_or_delete_owner_only_rows(self, conn, w):
        seed_private_rows(conn, w)
        with as_user(conn, w.main):
            assert conn.execute("update public.suppliers set amount_owed = 0").rowcount == 0
            assert conn.execute("update public.employees set monthly_salary = 0").rowcount == 0
            assert conn.execute("update public.tasks set status = 'Done'").rowcount == 0
        with as_user(conn, w.main):
            assert conn.execute("delete from public.tasks").rowcount == 0  # tasks have a DELETE grant; RLS hides the rows
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("delete from public.suppliers")  # no DELETE grant at all
        assert one(conn, "select amount_owed from public.suppliers") == 500
        assert one(conn, "select count(*) from public.tasks") == 1

    def test_owner_functions_reject_branch_user(self, conn, w):
        rid = add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100, cash=100)
        for sql, params in [("select public.void_daily_report(%s, 'x')", [rid]),
                            ("select * from public.app_balances('2026-10-05')", []),
                            ("select public.missing_report_count('2026-10-01','2026-10-05')", [])]:
            with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
                conn.execute(sql, params)

    def test_audit_log_unreadable_and_unwritable(self, conn, w):
        with as_user(conn, w.main):
            assert one(conn, "select count(*) from public.audit_log") == 0
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("insert into public.audit_log (action, table_name) values ('INSERT','x')")
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.owner):
            conn.execute("insert into public.audit_log (action, table_name) values ('INSERT','x')")

    def test_sees_only_own_branch(self, conn, w):
        with as_user(conn, w.main):
            names = [r[0] for r in q(conn, "select name from public.branches")]
        assert names == ["ALSAFA MAIN"]

    def test_owner_sees_all_ten_branches(self, conn, w):
        with as_user(conn, w.owner):
            assert one(conn, "select count(*) from public.branches") == 10


# ------------------------------------------------------------------ privilege escalation
class TestEscalation:
    def test_branch_user_cannot_change_own_role_branch_or_status(self, conn, w):
        for col, val in [("role", "'owner'"), ("branch_id", f"'{w.branch['JERNAS']}'"), ("is_active", "false")]:
            with as_user(conn, w.main):
                assert conn.execute(f"update public.profiles set {col} = {val} where user_id = %s", [w.main]).rowcount == 0
        row = q(conn, "select role, branch_id, is_active from public.profiles where user_id=%s", [w.main])[0]
        assert row == ("branch", w.branch["ALSAFA MAIN"], True)

    def test_branch_user_cannot_edit_another_profile(self, conn, w):
        with as_user(conn, w.main):
            assert conn.execute("update public.profiles set full_name='hacked' where user_id=%s", [w.jernas]).rowcount == 0
            assert one(conn, "select count(*) from public.profiles") == 1  # sees only self

    def test_branch_user_cannot_insert_profile(self, conn, w):
        uid = one(conn, "insert into auth.users (email) values ('x@example.test') returning id")
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("insert into public.profiles (user_id, full_name, role) values (%s,'Evil','owner')", [uid])

    def test_owner_cannot_change_own_role_or_status_via_api(self, conn, w):
        # a second owner exists so the last-owner guard is not what stops this
        other = w.make_user("owner", None, "Owner Two")
        for col, val in [("role", "'branch'"), ("is_active", "false")]:
            with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.owner):
                conn.execute(f"update public.profiles set {col} = {val} where user_id = %s", [w.owner])
        assert other

    def test_owner_may_manage_other_users(self, conn, w):
        with as_user(conn, w.owner):
            assert conn.execute("update public.profiles set is_active=false where user_id=%s", [w.main]).rowcount == 1
            assert conn.execute("update public.profiles set role='branch', branch_id=%s where user_id=%s",
                                [w.branch["SATWA"], w.jernas]).rowcount == 1
        assert one(conn, "select branch_id from public.profiles where user_id=%s", [w.jernas]) == w.branch["SATWA"]

    def test_user_id_is_immutable(self, conn, w):
        new = one(conn, "insert into auth.users (email) values ('y@example.test') returning id")
        with pytest.raises(E.CheckViolation):
            conn.execute("update public.profiles set user_id=%s where user_id=%s", [new, w.main])

    def test_operator_session_can_still_deactivate(self, conn, w):
        # no auth.uid(): SQL editor / provisioning script path keeps working
        assert conn.execute("update public.profiles set is_active=false where user_id=%s", [w.main]).rowcount == 1

    def test_last_owner_guard_still_active(self, conn, w):
        with pytest.raises(E.CheckViolation):
            conn.execute("update public.profiles set is_active=false where user_id=%s", [w.owner])


# ------------------------------------------------------------------ inactive and anonymous
class TestInactiveAndAnon:
    def deactivate(self, conn, uid):
        conn.execute("update public.profiles set is_active=false where user_id=%s", [uid])

    def test_inactive_branch_user_gets_nothing(self, conn, w):
        add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100, cash=100)
        self.deactivate(conn, w.main)
        with as_user(conn, w.main):
            assert one(conn, "select count(*) from public.daily_reports") == 0
            assert one(conn, "select count(*) from public.branches") == 0
            assert one(conn, "select count(*) from public.expense_categories") == 0
            assert one(conn, "select app.user_role()") is None
            assert one(conn, "select app.can_access_branch(%s)", [w.branch["ALSAFA MAIN"]]) is False

    def test_inactive_user_cannot_insert_reports(self, conn, w):
        self.deactivate(conn, w.main)
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("""insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received, created_by)
                            values ('2026-10-01', %s, 100, 1, 100, %s)""", [w.branch["ALSAFA MAIN"], w.main])

    def test_inactive_owner_loses_owner_powers(self, conn, w):
        w.make_user("owner", None, "Owner Two")
        self.deactivate(conn, w.owner)
        with as_user(conn, w.owner):
            assert one(conn, "select count(*) from public.branches") == 0
            assert one(conn, "select app.is_owner()") is False

    def test_user_without_profile_gets_nothing(self, conn, w):
        ghost = one(conn, "insert into auth.users (email) values ('ghost@example.test') returning id")
        with as_user(conn, ghost):
            assert one(conn, "select count(*) from public.branches") == 0
            assert one(conn, "select count(*) from public.profiles") == 0

    def test_anon_denied_everywhere(self, conn, w):
        for t in ["branches", "profiles", "daily_reports", "suppliers", "employees", "audit_log"]:
            with pytest.raises(E.InsufficientPrivilege), as_anon(conn):
                conn.execute(f"select * from public.{t}")
        with pytest.raises(E.InsufficientPrivilege), as_anon(conn):
            conn.execute("select app.is_owner()")


# ------------------------------------------------------------------ branch isolation at DB level
class TestBranchIsolationDb:
    def test_can_access_branch(self, conn, w):
        main, jer = w.branch["ALSAFA MAIN"], w.branch["JERNAS"]
        with as_user(conn, w.main):
            assert one(conn, "select app.can_access_branch(%s)", [main]) is True
            assert one(conn, "select app.can_access_branch(%s)", [jer]) is False
            assert one(conn, "select app.can_access_branch(null)") is False
        with as_user(conn, w.owner):
            assert all(one(conn, "select app.can_access_branch(%s)", [b]) for b in w.branch.values())

    def test_direct_record_id_of_other_branch_is_invisible(self, conn, w):
        rid = add_report(conn, w.branch["JERNAS"], "2026-10-01", 100, cash=100)
        with as_user(conn, w.main):
            assert q(conn, "select id from public.daily_reports where id=%s", [rid]) == []
            assert one(conn, "select count(*) from public.v_daily_reports_reconciled where id=%s", [rid]) == 0

    def test_cannot_insert_report_for_other_branch(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("""insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received, created_by)
                            values ('2026-10-01', %s, 100, 1, 100, %s)""", [w.branch["JERNAS"], w.main])

    def test_cannot_insert_report_attributed_to_someone_else(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("""insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received, created_by)
                            values ('2026-10-01', %s, 100, 1, 100, %s)""", [w.branch["ALSAFA MAIN"], w.jernas])

    def test_own_branch_insert_and_read_allowed(self, conn, w):
        with as_user(conn, w.main):
            conn.execute("""insert into public.daily_reports (report_date, branch_id, total_sales, order_count, cash_received, created_by)
                            values ('2026-10-01', %s, 100, 1, 100, %s)""", [w.branch["ALSAFA MAIN"], w.main])
            assert one(conn, "select count(*) from public.daily_reports") == 1

    def test_submitted_report_cannot_be_updated_or_deleted(self, conn, w):
        rid = add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100, cash=100)
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("update public.daily_reports set total_sales = 1 where id=%s", [rid])
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.main):
            conn.execute("delete from public.daily_reports where id=%s", [rid])
        # even the owner has no direct update/delete: corrections go through the audited void function
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.owner):
            conn.execute("update public.daily_reports set total_sales = 1 where id=%s", [rid])
        with pytest.raises(E.InsufficientPrivilege), as_user(conn, w.owner):
            conn.execute("delete from public.daily_reports where id=%s", [rid])
        assert one(conn, "select total_sales from public.daily_reports where id=%s", [rid]) == 100


# ------------------------------------------------------------------ audit of authorization events
class TestAudit:
    def test_log_access_denied_records_actor_from_session_not_parameter(self, conn, w):
        with as_user(conn, w.main):
            conn.execute("select app.log_access_denied('suppliers', 'read', %s)", [json.dumps({"path": "/api/v1/suppliers"})])
        row = q(conn, "select actor_user_id, action, table_name, new_values from public.audit_log where action='ACCESS_DENIED'")[0]
        assert row[0] == w.main and row[2] == "authorization"
        assert row[3]["module"] == "suppliers" and row[3]["action"] == "read"

    def test_anon_and_unknown_users_are_not_recorded(self, conn, w):
        ghost = one(conn, "insert into auth.users (email) values ('g@example.test') returning id")
        with as_user(conn, ghost):
            conn.execute("select app.log_access_denied('x','y')")
        assert one(conn, "select count(*) from public.audit_log where action='ACCESS_DENIED'") == 0
        with pytest.raises(E.InsufficientPrivilege), as_anon(conn):
            conn.execute("select app.log_access_denied('x','y')")

    def test_flood_protection(self, conn, w):
        with as_user(conn, w.main):
            for _ in range(60):
                conn.execute("select app.log_access_denied('x','y')")
        assert one(conn, "select count(*) from public.audit_log where action='ACCESS_DENIED'") == 30

    def test_oversized_detail_dropped_and_fields_truncated(self, conn, w):
        with as_user(conn, w.main):
            conn.execute("select app.log_access_denied(%s, %s, %s)", ["m" * 500, "a" * 500, json.dumps({"x": "z" * 5000})])
        nv = one(conn, "select new_values from public.audit_log where action='ACCESS_DENIED'")
        assert len(nv["module"]) == 64 and len(nv["action"]) == 32 and nv["detail"] == {}

    def test_users_cannot_edit_or_delete_audit_rows(self, conn, w):
        conn.execute("update public.profiles set full_name='Renamed' where user_id=%s", [w.main])  # makes an audit row
        for uid in (w.main, w.owner):
            with pytest.raises(E.InsufficientPrivilege), as_user(conn, uid):
                conn.execute("update public.audit_log set reason='x'")
            with pytest.raises(E.InsufficientPrivilege), as_user(conn, uid):
                conn.execute("delete from public.audit_log")
        with pytest.raises(E.InsufficientPrivilege):
            conn.execute("delete from public.audit_log")  # append-only trigger stops even the superuser

    def test_role_change_branch_reassignment_and_deactivation_are_audited_with_actor(self, conn, w):
        with as_user(conn, w.owner):
            conn.execute("update public.profiles set branch_id=%s where user_id=%s", [w.branch["SATWA"], w.main])
            conn.execute("select set_config('app.audit_reason','left company',true)")
            conn.execute("update public.profiles set is_active=false where user_id=%s", [w.main])
        rows = q(conn, """select actor_user_id, old_values->>'branch_id', new_values->>'branch_id',
                                 old_values->>'is_active', new_values->>'is_active', reason
                            from public.audit_log where table_name='profiles' and action='UPDATE' and record_id=%s order by id""", [str(w.main)])
        assert len(rows) == 2 and all(r[0] == w.owner for r in rows)
        assert rows[0][1] == str(w.branch["ALSAFA MAIN"]) and rows[0][2] == str(w.branch["SATWA"])
        assert (rows[1][3], rows[1][4], rows[1][5]) == ("true", "false", "left company")

    def test_audit_does_not_store_secrets(self, conn, w):
        conn.execute("update public.profiles set full_name='X' where user_id=%s", [w.main])
        text = json.dumps(q(conn, "select old_values, new_values from public.audit_log where table_name='profiles'"), default=str)
        assert "password" not in text.lower() and "token" not in text.lower()


# ------------------------------------------------------------------ migration 0018: first-login password change flag
class TestFirstLoginPasswordFlag:
    def test_defaults_false_and_there_is_no_password_column(self, conn, w):
        assert one(conn, "select must_change_password from public.profiles where user_id=%s", [w.main]) is False
        cols = {r[0] for r in q(conn, "select column_name from information_schema.columns where table_name='profiles'")}
        assert not {c for c in cols if "password" in c or "secret" in c} - {"must_change_password"}

    def test_user_cannot_clear_or_set_flag_by_direct_update(self, conn, w):
        conn.execute("update public.profiles set must_change_password = true where user_id=%s", [w.main])
        with as_user(conn, w.main):
            assert conn.execute("update public.profiles set must_change_password = false where user_id=%s",
                                [w.main]).rowcount == 0  # RLS: profile writes are owner-only
        assert one(conn, "select must_change_password from public.profiles where user_id=%s", [w.main]) is True

    def test_complete_password_change_clears_only_the_callers_flag(self, conn, w):
        conn.execute("update public.profiles set must_change_password = true where user_id in (%s, %s)", [w.main, w.jernas])
        with as_user(conn, w.main):
            conn.execute("select app.complete_password_change()")
        assert one(conn, "select must_change_password from public.profiles where user_id=%s", [w.main]) is False
        assert one(conn, "select must_change_password from public.profiles where user_id=%s", [w.jernas]) is True

    def test_function_not_callable_by_anon(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege), as_anon(conn):
            conn.execute("select app.complete_password_change()")

    def test_branch_isolation_is_unchanged_while_flag_is_set(self, conn, w):
        conn.execute("update public.profiles set must_change_password = true where user_id=%s", [w.main])
        with as_user(conn, w.main):
            assert {r[0] for r in conn.execute("select id from public.branches").fetchall()} == {w.branch["ALSAFA MAIN"]}


# ------------------------------------------------------------------ migration 0019: settings (own profile, preferences)
class TestUserSettings:
    def test_update_own_profile_changes_only_name_phone_photo(self, conn, w):
        before = q(conn, "select role, branch_id, is_active from public.profiles where user_id=%s", [w.main])
        with as_user(conn, w.main):
            conn.execute("select app.update_own_profile('New Name', ' +971 50 123 4567 ', null)")
        assert q(conn, "select role, branch_id, is_active from public.profiles where user_id=%s", [w.main]) == before
        assert q(conn, "select full_name, phone from public.profiles where user_id=%s", [w.main]) == [
            ("New Name", "+971 50 123 4567")]

    def test_update_own_profile_never_touches_other_rows(self, conn, w):
        other = one(conn, "select full_name from public.profiles where user_id=%s", [w.jernas])
        with as_user(conn, w.main):
            conn.execute("select app.update_own_profile('Someone', null, null)")
        assert one(conn, "select full_name from public.profiles where user_id=%s", [w.jernas]) == other

    def test_update_own_profile_not_callable_by_anon(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege), as_anon(conn):
            conn.execute("select app.update_own_profile('x', null, null)")

    def test_avatar_path_must_be_inside_own_folder(self, conn, w):
        bad = f"{w.jernas}/avatar-{uuid.uuid4()}.png"
        with pytest.raises(E.CheckViolation), as_user(conn, w.main):
            conn.execute("select app.update_own_profile('Name', null, %s)", [bad])

    def test_bad_phone_rejected(self, conn, w):
        with pytest.raises(E.CheckViolation), as_user(conn, w.main):
            conn.execute("select app.update_own_profile('Name', 'abc', null)")

    def test_preferences_are_private_per_user(self, conn, w):
        with as_user(conn, w.main):
            conn.execute("insert into public.user_preferences (user_id, preferences) values (%s, '{\"theme\":\"dark\"}')", [w.main])
        with as_user(conn, w.jernas):
            assert conn.execute("select 1 from public.user_preferences").fetchall() == []
            with pytest.raises(E.InsufficientPrivilege):
                conn.execute("insert into public.user_preferences (user_id) values (%s)", [w.main])

    def test_preferences_not_visible_to_anon(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege), as_anon(conn):
            conn.execute("select * from public.user_preferences")
