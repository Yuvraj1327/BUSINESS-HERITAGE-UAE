"""Step 2 database tests. Numbered classes match the 18 required test areas (plus extra hardening tests)."""
import json
import threading
import uuid

import psycopg
import pytest
from psycopg import errors as E

from conftest import add_report, as_anon, as_user, one, q

BRANCHES = ["ALSAFA MAIN", "JERNAS", "SATWA", "BURDUBAI", "NDL",
            "AL BARSHA", "MIRDIF", "AL JADDAF", "KARAMA", "SALES TEAM"]
CATEGORIES = {"Detergent & chemicals", "Utilities", "Rent", "Repairs", "Transport", "Packaging", "Salaries"}
APP_TABLES = {"branches", "expense_categories", "profiles", "opening_balances", "opening_branch_cash",
              "daily_reports", "head_office_expenses", "suppliers", "employees", "tasks", "trade_licenses",
              "rental_agreements", "pdc_cheques", "audit_log",
              "supplier_entries", "pos_settlements", "cash_transfers", "license_renewals", "alerts", "service_categories", "customers", "orders", "order_payments", "order_status_history"}


def cheques(n, rent, bank="ENBD", first="2026-10-01", prefix="C"):
    """Test helper: equal split, last takes the remainder (the real split rule lives in the backend, Step 10)."""
    base = round(rent / n, 2)
    out = []
    for k in range(n):
        amt = base if k < n - 1 else round(rent - base * (n - 1), 2)
        out.append({"cheque_no": f"{prefix}{k+1}", "bank": bank, "cheque_date": first, "amount": amt})
    return out


# ---------------------------------------------------------------- 1. fresh migration
class Test01FreshMigration:
    def test_all_tables_exist_with_rls(self, conn):
        rows = q(conn, """select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace
                          where n.nspname='public' and c.relkind='r'""")
        got = {r[0]: r[1] for r in rows}
        assert set(got) == APP_TABLES
        assert all(got.values()), [t for t, v in got.items() if not v]

    def test_supabase_schemas_untouched(self, conn):
        # Our migrations must not create or alter anything in auth beyond referencing it.
        assert q(conn, "select table_name from information_schema.tables where table_schema='auth'") == [("users",)]

    def test_api_role_is_restricted(self, conn):
        r = q(conn, "select rolcanlogin, rolinherit, rolbypassrls, rolsuper from pg_roles where rolname='app_api'")[0]
        assert r == (False, False, False, False)
        assert one(conn, "select pg_has_role('app_api','authenticated','member')") is True

    def test_security_definer_functions_pin_search_path(self, conn):
        rows = q(conn, """select p.proname, p.proconfig from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                          where p.prosecdef and n.nspname in ('public','app')""")
        assert rows, "expected SECURITY DEFINER functions"
        for name, cfg in rows:
            assert cfg and any(c.startswith("search_path=") for c in cfg), name

    def test_no_public_execute_on_functions(self, conn):
        bad = q(conn, """select p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                         where n.nspname in ('public','app')
                           and (has_function_privilege('anon', p.oid, 'execute') or has_function_privilege('public', p.oid, 'execute'))""")
        assert bad == []

    def test_sensitive_identifiers_not_stored(self, conn):
        cols = {r[0] for r in q(conn, "select column_name from information_schema.columns where table_name='employees'")}
        assert not any("passport_no" in c or "passport_number" in c or "emirates" in c or "eid" in c for c in cols)


# ---------------------------------------------------------------- 2. seed
class Test02Seed:
    def test_ten_branches_in_order(self, conn):
        rows = q(conn, "select name, sort_order, is_active from public.branches order by sort_order")
        assert [r[0] for r in rows] == BRANCHES
        assert [r[1] for r in rows] == list(range(1, 11))
        assert all(r[2] for r in rows)

    def test_seven_categories(self, conn):
        assert {r[0] for r in q(conn, "select name from public.expense_categories")} == CATEGORIES

    def test_seed_is_idempotent(self, conn):
        from conftest import MIGRATIONS
        seed = [m for m in MIGRATIONS if m.name.startswith("0009")][0].read_text()
        conn.execute(seed)
        conn.execute(seed)
        assert one(conn, "select count(*) from public.branches") == 10
        assert one(conn, "select count(*) from public.expense_categories") == 7

    def test_no_fake_business_data(self, conn):
        for t in ["daily_reports", "head_office_expenses", "suppliers", "employees", "opening_balances",
                  "opening_branch_cash", "trade_licenses", "rental_agreements", "pdc_cheques", "tasks", "profiles"]:
            assert one(conn, f"select count(*) from public.{t}") == 0, t


# ---------------------------------------------------------------- 3. unique branch names
class Test03UniqueBranch:
    def test_duplicate_branch_name_rejected(self, conn):
        with pytest.raises(E.UniqueViolation):
            with conn.transaction():
                conn.execute("insert into public.branches (name, sort_order) values ('JERNAS', 99)")

    def test_blank_name_rejected(self, conn):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.branches (name, sort_order) values ('  ', 99)")


# ---------------------------------------------------------------- 4. duplicate daily reports
class Test04DuplicateReports:
    def test_duplicate_same_branch_same_day_rejected(self, conn, w):
        add_report(conn, w.branch["SATWA"], "2026-10-05", 100)
        with pytest.raises(E.UniqueViolation):
            with conn.transaction():
                add_report(conn, w.branch["SATWA"], "2026-10-05", 200)

    def test_same_day_other_branch_allowed(self, conn, w):
        add_report(conn, w.branch["SATWA"], "2026-10-05", 100)
        add_report(conn, w.branch["NDL"], "2026-10-05", 100)

    def test_voided_report_frees_slot_for_resubmission(self, conn, w):
        rid = add_report(conn, w.branch["SATWA"], "2026-10-05", 100)
        with as_user(conn, w.owner):
            conn.execute("select public.void_daily_report(%s, 'wrong amount entered')", [rid])
        add_report(conn, w.branch["SATWA"], "2026-10-05", 120)
        assert one(conn, "select count(*) from public.daily_reports where branch_id=%s and report_date='2026-10-05'",
                   [w.branch["SATWA"]]) == 2

    def test_concurrent_submissions_cannot_duplicate(self, dsn, conn):
        bid = one(conn, "select id from public.branches where name='KARAMA'")
        conn.rollback()
        d = "2020-01-01"
        sql = """insert into public.daily_reports (report_date, branch_id, total_sales) values (%s, %s, 50)"""
        c1, c2 = psycopg.connect(dsn), psycopg.connect(dsn)
        result = {}

        def second():
            try:
                c2.execute(sql, [d, bid])
                c2.commit()
                result["c2"] = "inserted"
            except E.UniqueViolation:
                c2.rollback()
                result["c2"] = "unique_violation"

        try:
            c1.execute(sql, [d, bid])              # first transaction holds the slot, not yet committed
            t = threading.Thread(target=second)
            t.start()
            t.join(timeout=0.5)
            assert t.is_alive(), "second insert should wait on the first"
            c1.commit()
            t.join(timeout=10)
            assert result["c2"] == "unique_violation"
            assert one(c1, "select count(*) from public.daily_reports where branch_id=%s and report_date=%s",
                       [bid, d]) == 1
        finally:
            c1.rollback(); c2.rollback()
            c1.execute("delete from public.daily_reports where report_date=%s", [d]); c1.commit()
            c1.close(); c2.close()


# ---------------------------------------------------------------- 5. negative amounts / sales > 0
NEG_COLS = ["cash_received", "pos_amount", "bank_transfer", "link_payment", "shop_expenses", "order_count"]


class Test05AmountRules:
    @pytest.mark.parametrize("col", NEG_COLS)
    def test_negative_rejected(self, conn, w, col):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute(f"insert into public.daily_reports (report_date, branch_id, total_sales, {col}) "
                             f"values ('2026-10-01', %s, 100, -1)", [w.branch["MIRDIF"]])

    def test_negative_shop_savings_rejected(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                add_report(conn, w.branch["MIRDIF"], "2026-10-01", 100, exp=10, sav=-1)

    @pytest.mark.parametrize("sales", [0, -5])
    def test_sales_must_be_positive(self, conn, w, sales):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                add_report(conn, w.branch["MIRDIF"], "2026-10-01", sales)

    def test_negative_expense_and_supplier_and_opening_rejected(self, conn, w):
        cat = w.category()
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.head_office_expenses (expense_date, category_id, amount, paid_from) "
                             "values ('2026-10-01', %s, -1, 'ENBD')", [cat])
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.suppliers (name, amount_owed) values ('S', -1)")
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.opening_branch_cash (branch_id, amount) values (%s, -1)",
                             [w.branch["NDL"]])
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.opening_balances (as_of_date, receipts_bank, enbd_balance) "
                             "values ('2026-09-30','ENBD',-1)")


# ---------------------------------------------------------------- 6. savings > expenses
class Test06Savings:
    def test_savings_exceeding_expenses_rejected(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                add_report(conn, w.branch["AL JADDAF"], "2026-10-01", 100, exp=10, sav=10.01)

    def test_savings_equal_expenses_allowed(self, conn, w):
        add_report(conn, w.branch["AL JADDAF"], "2026-10-01", 100, exp=10, sav=10)


# ---------------------------------------------------------------- 7. future dates (Dubai)
class Test07FutureDate:
    def test_today_dubai_allowed_tomorrow_rejected(self, conn, w):
        today = one(conn, "select app.dubai_today()")
        add_report(conn, w.branch["BURDUBAI"], today, 100)
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                add_report(conn, w.branch["BURDUBAI"], one(conn, "select app.dubai_today() + 1"), 100)

    def test_dubai_boundary_logic(self, conn):
        # The rule is anchored to Asia/Dubai (UTC+4), not UTC.
        dubai = one(conn, "select (now() at time zone 'Asia/Dubai')::date")
        assert one(conn, "select app.dubai_today()") == dubai

    def test_employee_future_leave_start_rejected(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.employees (full_name, branch_id, status, leave_start) "
                             "values ('X', %s, 'Leave', app.dubai_today() + 1)", [w.branch["NDL"]])


# ---------------------------------------------------------------- 8. owner access
class Test08Owner:
    def test_owner_sees_all_branches_and_reports(self, conn, w):
        add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        add_report(conn, w.branch["JERNAS"], "2026-10-01", 200)
        with as_user(conn, w.owner):
            assert one(conn, "select count(*) from public.branches") == 10
            assert one(conn, "select count(*) from public.daily_reports") == 2
            assert one(conn, "select count(*) from public.profiles") == 3

    def test_owner_can_insert_report_for_any_branch(self, conn, w):
        with as_user(conn, w.owner):
            add_report(conn, w.branch["SALES TEAM"], "2026-10-01", 100)

    def test_owner_can_manage_owner_only_tables(self, conn, w):
        with as_user(conn, w.owner):
            conn.execute("insert into public.suppliers (name, amount_owed) values ('Test Supplier', 10)")
            conn.execute("insert into public.employees (full_name, branch_id) values ('Test Emp', %s)", [w.branch["NDL"]])
            conn.execute("insert into public.trade_licenses (branch_id, license_no, expiry_date) values (%s,'L-1','2027-01-01')",
                         [w.branch["NDL"]])
            conn.execute("insert into public.tasks (title) values ('t')")
            conn.execute("update public.suppliers set amount_owed = 0 where name = 'Test Supplier'")
            assert one(conn, "select count(*) from public.suppliers") == 1

    def test_last_owner_cannot_be_demoted_or_deactivated(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("update public.profiles set is_active=false where user_id=%s", [w.owner])
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("update public.profiles set role='branch', branch_id=%s where user_id=%s",
                             [w.branch["NDL"], w.owner])

    def test_profile_role_branch_consistency(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                w.make_user("owner", "NDL", "bad owner")
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                w.make_user("branch", None, "bad branch")


# ---------------------------------------------------------------- 9. branch user own-branch access
class Test09BranchOwn:
    def test_branch_sees_only_own_branch_row_and_profile(self, conn, w):
        with as_user(conn, w.main):
            assert [r[0] for r in q(conn, "select name from public.branches")] == ["ALSAFA MAIN"]
            assert [r[0] for r in q(conn, "select user_id from public.profiles")] == [w.main]
            assert one(conn, "select count(*) from public.expense_categories") == 7

    def test_branch_can_insert_and_read_own_report(self, conn, w):
        with as_user(conn, w.main):
            add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100, cash=100)
            rows = q(conn, "select branch_id, created_by from public.daily_reports")
            assert rows == [(w.branch["ALSAFA MAIN"], w.main)]
            assert q(conn, "select check_label from public.v_daily_reports_reconciled") == [("Matches",)]

    def test_branch_cannot_forge_created_by(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("insert into public.daily_reports (report_date, branch_id, total_sales, created_by) "
                             "values ('2026-10-01', %s, 100, %s)", [w.branch["ALSAFA MAIN"], w.jernas])

    def test_branch_cannot_submit_pre_voided_report(self, conn, w):
        with pytest.raises((E.InsufficientPrivilege, E.CheckViolation)):
            with as_user(conn, w.main):
                conn.execute("insert into public.daily_reports (report_date, branch_id, total_sales, voided_at, void_reason) "
                             "values ('2026-10-01', %s, 100, now(), 'x')", [w.branch["ALSAFA MAIN"]])

    def test_branch_missing_report_list_is_own_branch_only(self, conn, w):
        with as_user(conn, w.main):
            assert [r[1] for r in q(conn, "select * from public.missing_report_branches('2026-10-01')")] == ["ALSAFA MAIN"]


# ---------------------------------------------------------------- 10. cross-branch denial
class Test10CrossBranch:
    def test_cannot_read_other_branch_reports(self, conn, w):
        add_report(conn, w.branch["JERNAS"], "2026-10-01", 500)
        with as_user(conn, w.main):
            assert one(conn, "select count(*) from public.daily_reports") == 0
            assert one(conn, "select count(*) from public.v_daily_reports_reconciled") == 0

    def test_cannot_insert_for_other_branch(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                add_report(conn, w.branch["JERNAS"], "2026-10-01", 100)

    def test_cannot_see_other_profiles(self, conn, w):
        with as_user(conn, w.main):
            assert one(conn, "select count(*) from public.profiles where user_id = %s", [w.jernas]) == 0

    def test_inactive_user_loses_all_access(self, conn, w):
        add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        conn.execute("update public.profiles set is_active=false where user_id=%s", [w.main])
        with as_user(conn, w.main):
            assert one(conn, "select count(*) from public.daily_reports") == 0
            assert one(conn, "select count(*) from public.branches") == 0
            assert one(conn, "select count(*) from public.expense_categories") == 0
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-02", 100)

    def test_user_without_profile_has_no_access(self, conn, w):
        stranger = one(conn, "insert into auth.users (email) values ('stranger@example.test') returning id")
        add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        with as_user(conn, stranger):
            for t in ["branches", "daily_reports", "profiles", "expense_categories"]:
                assert one(conn, f"select count(*) from public.{t}") == 0, t


# ---------------------------------------------------------------- 11. branch update/delete denial
class Test11NoEditDelete:
    def test_branch_cannot_update_or_delete_reports(self, conn, w):
        with as_user(conn, w.main):
            add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("update public.daily_reports set total_sales = 1")
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("delete from public.daily_reports")

    def test_not_even_owner_can_update_or_delete_reports_directly(self, conn, w):
        add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.owner):
                conn.execute("update public.daily_reports set total_sales = 1")
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.owner):
                conn.execute("delete from public.daily_reports")

    def test_branch_cannot_escalate_privileges(self, conn, w):
        with as_user(conn, w.main):
            r = conn.execute("update public.profiles set role='owner', branch_id=null where user_id=%s", [w.main])
            assert r.rowcount == 0           # RLS hides the row from UPDATE
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("insert into public.profiles (user_id, full_name, role) values (%s,'x','owner')",
                             [one(conn, "insert into auth.users (email) values ('e@example.test') returning id")])
        assert q(conn, "select role, branch_id from public.profiles where user_id=%s", [w.main]) == [("branch", w.branch["ALSAFA MAIN"])]

    def test_branch_cannot_change_own_branch_assignment(self, conn, w):
        with as_user(conn, w.main):
            r = conn.execute("update public.profiles set branch_id=%s where user_id=%s", [w.branch["JERNAS"], w.main])
            assert r.rowcount == 0

    def test_branch_cannot_void(self, conn, w):
        rid = add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("select public.void_daily_report(%s, 'because')", [rid])

    def test_void_requires_reason_and_keeps_row(self, conn, w):
        rid = add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        with pytest.raises(E.CheckViolation):
            with as_user(conn, w.owner):
                conn.execute("select public.void_daily_report(%s, '  ')", [rid])
        with as_user(conn, w.owner):
            conn.execute("select public.void_daily_report(%s, 'duplicate entry')", [rid])
        assert q(conn, "select void_reason, voided_by from public.daily_reports where id=%s", [rid]) == [("duplicate entry", w.owner)]
        assert one(conn, "select count(*) from public.v_daily_reports_reconciled") == 0


# ---------------------------------------------------------------- 12. anonymous denial
class Test12Anon:
    @pytest.mark.parametrize("table", sorted(APP_TABLES) + ["v_daily_reports_reconciled"])
    def test_anon_cannot_read(self, conn, table):
        with pytest.raises(E.InsufficientPrivilege):
            with as_anon(conn):
                conn.execute(f"select * from public.{table}")

    @pytest.mark.parametrize("table", ["daily_reports", "branches", "profiles", "suppliers"])
    def test_anon_cannot_write(self, conn, table):
        with pytest.raises(E.InsufficientPrivilege):
            with as_anon(conn):
                conn.execute(f"delete from public.{table}")

    def test_anon_cannot_call_functions(self, conn):
        with pytest.raises(E.InsufficientPrivilege):
            with as_anon(conn):
                conn.execute("select * from public.app_balances()")
        with pytest.raises(E.InsufficientPrivilege):
            with as_anon(conn):
                conn.execute("select app.is_owner()")


# ---------------------------------------------------------------- 13. employee / owner-only privacy
class Test13Privacy:
    def test_branch_user_sees_nothing_owner_only(self, conn, w):
        conn.execute("insert into public.employees (full_name, branch_id, monthly_salary, visa_expiry, passport_expiry) "
                     "values ('Emp', %s, 1234, '2027-01-01', '2028-01-01')", [w.branch["ALSAFA MAIN"]])
        conn.execute("insert into public.suppliers (name, amount_owed) values ('Sup', 5)")
        conn.execute("insert into public.trade_licenses (branch_id, license_no, expiry_date) values (%s,'L','2027-01-01')",
                     [w.branch["ALSAFA MAIN"]])
        conn.execute("insert into public.tasks (title, branch_id) values ('t', %s)", [w.branch["ALSAFA MAIN"]])
        conn.execute("insert into public.opening_balances (as_of_date, receipts_bank) values ('2026-09-30','ENBD')")
        conn.execute("insert into public.opening_branch_cash (branch_id, amount) values (%s, 10)", [w.branch["ALSAFA MAIN"]])
        conn.execute("insert into public.head_office_expenses (expense_date, category_id, amount, paid_from) "
                     "values ('2026-10-01', %s, 5, 'ENBD')", [w.category()])
        with as_user(conn, w.owner):
            ra = one(conn, "select public.create_rental_agreement(%s,'Landlord','U1','2026-10-01','2027-09-30',1200,%s::jsonb)",
                     [w.branch["ALSAFA MAIN"], json.dumps(cheques(2, 1200))])
        for t in ["employees", "suppliers", "trade_licenses", "tasks", "opening_balances", "opening_branch_cash",
                  "head_office_expenses", "rental_agreements", "pdc_cheques", "audit_log"]:
            with as_user(conn, w.main):
                assert one(conn, f"select count(*) from public.{t}") == 0, t
        # and the writes are refused too
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("insert into public.employees (full_name, branch_id) values ('x', %s)", [w.branch["ALSAFA MAIN"]])
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("select * from public.app_balances()")

    def test_owner_sees_salary(self, conn, w):
        conn.execute("insert into public.employees (full_name, branch_id, monthly_salary) values ('Emp', %s, 1234)",
                     [w.branch["NDL"]])
        with as_user(conn, w.owner):
            assert one(conn, "select monthly_salary from public.employees") == 1234

    def test_employee_leave_rule(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.employees (full_name, branch_id, status) values ('A', %s, 'Leave')", [w.branch["NDL"]])
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.employees (full_name, branch_id, status, leave_start) "
                             "values ('A', %s, 'Active', '2026-10-01')", [w.branch["NDL"]])
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.employees (full_name, branch_id, status) values ('A', %s, 'Retired')", [w.branch["NDL"]])


# ---------------------------------------------------------------- 14. financial transaction integrity
class Test14FinancialIntegrity:
    def test_expense_source_must_be_cash_enbd_adcb(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.head_office_expenses (expense_date, category_id, amount, paid_from) "
                             "values ('2026-10-01', %s, 5, 'PayPal')", [w.category()])

    def test_opening_balances_is_single_row(self, conn):
        conn.execute("insert into public.opening_balances (as_of_date, receipts_bank) values ('2026-09-30','ENBD')")
        with pytest.raises(E.UniqueViolation):
            with conn.transaction():
                conn.execute("insert into public.opening_balances (as_of_date, receipts_bank) values ('2026-09-30','ADCB')")
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.opening_balances (id, as_of_date, receipts_bank) values (2,'2026-09-30','ADCB')")

    def test_opening_branch_cash_one_row_per_branch(self, conn, w):
        conn.execute("insert into public.opening_branch_cash (branch_id, amount) values (%s, 1)", [w.branch["NDL"]])
        with pytest.raises(E.UniqueViolation):
            with conn.transaction():
                conn.execute("insert into public.opening_branch_cash (branch_id, amount) values (%s, 2)", [w.branch["NDL"]])

    def test_expense_edit_limited_to_saving_flag(self, conn, w):
        eid = one(conn, "insert into public.head_office_expenses (expense_date, category_id, amount, paid_from) "
                        "values ('2026-10-01', %s, 5, 'ENBD') returning id", [w.category()])
        with as_user(conn, w.owner):
            conn.execute("update public.head_office_expenses set is_saving = true where id=%s", [eid])
        for stmt in ["update public.head_office_expenses set amount = 999",
                     "update public.head_office_expenses set paid_from = 'ADCB'",
                     "delete from public.head_office_expenses"]:
            with pytest.raises(E.InsufficientPrivilege):
                with as_user(conn, w.owner):
                    conn.execute(stmt)

    def test_no_hard_delete_on_financial_tables_even_for_owner(self, conn, w):
        for t in ["suppliers", "employees", "trade_licenses", "rental_agreements", "pdc_cheques", "opening_balances",
                  "opening_branch_cash", "head_office_expenses", "daily_reports", "branches", "profiles", "audit_log"]:
            with pytest.raises(E.InsufficientPrivilege):
                with as_user(conn, w.owner):
                    conn.execute(f"delete from public.{t}")

    def test_foreign_keys_restrict_delete(self, conn, w):
        add_report(conn, w.branch["NDL"], "2026-10-01", 100)
        with pytest.raises(E.ForeignKeyViolation):
            with conn.transaction():
                conn.execute("delete from public.branches where name='NDL'")

    def test_void_expense_requires_reason_and_is_owner_only(self, conn, w):
        eid = one(conn, "insert into public.head_office_expenses (expense_date, category_id, amount, paid_from) "
                        "values ('2026-10-01', %s, 5, 'ENBD') returning id", [w.category()])
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("select public.void_head_office_expense(%s,'x')", [eid])
        with pytest.raises(E.CheckViolation):
            with as_user(conn, w.owner):
                conn.execute("select public.void_head_office_expense(%s,'')", [eid])
        with as_user(conn, w.owner):
            conn.execute("select public.void_head_office_expense(%s,'entered twice')", [eid])
        assert one(conn, "select voided_at is not null from public.head_office_expenses where id=%s", [eid])


# ---------------------------------------------------------------- 15. rental agreement + cheque consistency
class Test15Rental:
    def create(self, conn, w, n=4, rent=12000, uid=None, **kw):
        with as_user(conn, uid or w.owner):
            return one(conn, "select public.create_rental_agreement(%s,'Landlord','Shop 1','2026-10-01','2027-09-30',%s,%s::jsonb)",
                       [w.branch["ALSAFA MAIN"], rent, json.dumps(kw["ch"] if "ch" in kw else cheques(n, rent))])

    def test_create_is_atomic_and_total_matches_rent(self, conn, w):
        aid = self.create(conn, w, n=3, rent=10000)   # 3333.33 + 3333.33 + 3333.34
        assert one(conn, "select count(*) from public.pdc_cheques where agreement_id=%s", [aid]) == 3
        assert one(conn, "select sum(amount) from public.pdc_cheques where agreement_id=%s", [aid]) == 10000
        assert set(r[0] for r in q(conn, "select status from public.pdc_cheques")) == {"Pending"}

    def test_total_mismatch_rolls_back_everything(self, conn, w):
        bad = cheques(4, 12000); bad[0]["amount"] += 1
        with pytest.raises(E.CheckViolation):
            self.create(conn, w, ch=bad)
        assert one(conn, "select count(*) from public.rental_agreements") == 0
        assert one(conn, "select count(*) from public.pdc_cheques") == 0

    def test_invalid_cheque_midway_rolls_back_agreement(self, conn, w):
        bad = cheques(4, 12000); bad[3]["bank"] = "MASHREQ"
        with pytest.raises(E.CheckViolation):
            self.create(conn, w, ch=bad)
        assert one(conn, "select count(*) from public.rental_agreements") == 0

    @pytest.mark.parametrize("n", [0, 13])
    def test_cheque_count_limits(self, conn, w, n):
        with pytest.raises(E.CheckViolation):
            self.create(conn, w, ch=cheques(max(n, 1), 12000)[:n] if n else [], rent=12000)

    @pytest.mark.parametrize("n", [1, 12])
    def test_cheque_count_edges_allowed(self, conn, w, n):
        self.create(conn, w, n=n, rent=12000)

    def test_duplicate_cheque_number_in_agreement_rejected(self, conn, w):
        dup = cheques(2, 1000); dup[1]["cheque_no"] = dup[0]["cheque_no"]
        with pytest.raises(E.UniqueViolation):
            self.create(conn, w, ch=dup, rent=1000)

    def test_agreement_dates_validated(self, conn, w):
        with pytest.raises(E.CheckViolation):
            with as_user(conn, w.owner):
                conn.execute("select public.create_rental_agreement(%s,'L','U','2027-09-30','2026-10-01',1000,%s::jsonb)",
                             [w.branch["ALSAFA MAIN"], json.dumps(cheques(1, 1000))])

    def test_branch_user_cannot_create(self, conn, w):
        with pytest.raises(E.InsufficientPrivilege):
            self.create(conn, w, uid=w.main)

    def test_renewal_rules_and_history_preserved(self, conn, w):
        aid = self.create(conn, w, n=4, rent=12000)
        conn.execute("update public.pdc_cheques set status='Cleared' where agreement_id=%s and cheque_no='C1'", [aid])
        new_ch = cheques(4, 12000, first="2027-10-01", prefix="N")
        with as_user(conn, w.owner):
            nid = one(conn, "select public.renew_rental_agreement(%s,%s::jsonb)", [aid, json.dumps(new_ch)])
        assert q(conn, "select start_date, end_date, annual_rent, status, renewed_from_id from public.rental_agreements where id=%s", [nid]) \
            == [(__import__("datetime").date(2027, 10, 1), __import__("datetime").date(2028, 9, 30), 12000, "Active", aid)]
        assert one(conn, "select status from public.rental_agreements where id=%s", [aid]) == "Renewed"
        assert one(conn, "select count(*) from public.pdc_cheques where agreement_id=%s", [aid]) == 4       # history kept
        assert one(conn, "select status from public.pdc_cheques where agreement_id=%s and cheque_no='C1'", [aid]) == "Cleared"
        assert set(r[0] for r in q(conn, "select status from public.pdc_cheques where agreement_id=%s", [nid])) == {"Pending"}

    def test_renewal_guards(self, conn, w):
        aid = self.create(conn, w, n=4, rent=12000)
        with pytest.raises(E.CheckViolation):      # wrong cheque count
            with as_user(conn, w.owner):
                conn.execute("select public.renew_rental_agreement(%s,%s::jsonb)", [aid, json.dumps(cheques(3, 12000, prefix="N"))])
        with as_user(conn, w.owner):
            conn.execute("select public.renew_rental_agreement(%s,%s::jsonb)", [aid, json.dumps(cheques(4, 12000, prefix="N"))])
        with pytest.raises(E.CheckViolation):      # cannot renew twice
            with as_user(conn, w.owner):
                conn.execute("select public.renew_rental_agreement(%s,%s::jsonb)", [aid, json.dumps(cheques(4, 12000, prefix="M"))])


# ---------------------------------------------------------------- 16. cheque status validation
class Test16ChequeStatus:
    def one_cheque(self, conn, w):
        with as_user(conn, w.owner):
            aid = one(conn, "select public.create_rental_agreement(%s,'L','U','2026-10-01','2027-09-30',1000,%s::jsonb)",
                      [w.branch["ALSAFA MAIN"], json.dumps(cheques(1, 1000))])
        return one(conn, "select id from public.pdc_cheques where agreement_id=%s", [aid])

    def test_invalid_status_rejected(self, conn, w):
        cid = self.one_cheque(conn, w)
        with pytest.raises(E.CheckViolation):
            with as_user(conn, w.owner):
                conn.execute("update public.pdc_cheques set status='Void' where id=%s", [cid])

    def test_invalid_bank_and_amount_rejected(self, conn, w):
        cid = self.one_cheque(conn, w)
        with pytest.raises(E.CheckViolation):
            with as_user(conn, w.owner):
                conn.execute("update public.pdc_cheques set bank='X' where id=%s", [cid])
        with pytest.raises(E.CheckViolation):
            with as_user(conn, w.owner):
                conn.execute("update public.pdc_cheques set amount=0 where id=%s", [cid])

    def test_cleared_at_is_maintained(self, conn, w):
        cid = self.one_cheque(conn, w)
        with as_user(conn, w.owner):
            conn.execute("update public.pdc_cheques set status='Cleared' where id=%s", [cid])
        assert one(conn, "select cleared_at is not null from public.pdc_cheques where id=%s", [cid])
        # Step 10: a cleared cheque is final (history is never overwritten); a bounced one needs a replacement cheque
        with pytest.raises(E.CheckViolation):
            with as_user(conn, w.owner):
                conn.execute("update public.pdc_cheques set status='Bounced' where id=%s", [cid])
        with as_user(conn, w.owner):
            aid2 = one(conn, "select public.create_rental_agreement(%s,'L','U','2026-10-01','2027-09-30',1000,%s::jsonb)",
                       [w.branch["ALSAFA MAIN"], json.dumps(cheques(1, 1000, prefix="D"))])
        cid2 = one(conn, "select id from public.pdc_cheques where agreement_id=%s", [aid2])
        with as_user(conn, w.owner):
            conn.execute("update public.pdc_cheques set status='Bounced' where id=%s", [cid2])
        assert one(conn, "select cleared_at is null and bounced_at is not null from public.pdc_cheques where id=%s", [cid2])

    def test_task_status_validation(self, conn):
        with pytest.raises(E.CheckViolation):
            with conn.transaction():
                conn.execute("insert into public.tasks (title, status) values ('t', 'Blocked')")


# ---------------------------------------------------------------- 17. audit log
class Test17Audit:
    def test_insert_update_are_logged_with_actor_and_values(self, conn, w):
        with as_user(conn, w.owner):
            eid = one(conn, "insert into public.head_office_expenses (expense_date, category_id, amount, paid_from) "
                            "values ('2026-10-01', %s, 5, 'ENBD') returning id", [w.category()])
            conn.execute("update public.head_office_expenses set is_saving=true where id=%s", [eid])
        rows = q(conn, "select action, actor_user_id, old_values, new_values from public.audit_log "
                       "where table_name='head_office_expenses' and record_id=%s order by id", [str(eid)])
        assert [r[0] for r in rows] == ["INSERT", "UPDATE"]
        assert all(r[1] == w.owner for r in rows)
        assert rows[1][2]["is_saving"] is False and rows[1][3]["is_saving"] is True

    def test_void_reason_recorded(self, conn, w):
        rid = add_report(conn, w.branch["NDL"], "2026-10-01", 100)
        with as_user(conn, w.owner):
            conn.execute("select public.void_daily_report(%s,'keyed on wrong branch')", [rid])
        reasons = [r[0] for r in q(conn, "select reason from public.audit_log where table_name='daily_reports' "
                                         "and record_id=%s and action='UPDATE'", [str(rid)])]
        assert reasons == ["keyed on wrong branch"]

    def test_branch_submission_is_audited_even_without_audit_privileges(self, conn, w):
        with as_user(conn, w.main):
            rid = add_report(conn, w.branch["ALSAFA MAIN"], "2026-10-01", 100)
        assert one(conn, "select count(*) from public.audit_log where table_name='daily_reports' and record_id=%s",
                   [str(rid)]) == 1

    def test_audit_log_is_append_only(self, conn, w):
        add_report(conn, w.branch["NDL"], "2026-10-01", 100)
        for stmt in ["update public.audit_log set reason='x'", "delete from public.audit_log", "truncate public.audit_log"]:
            with pytest.raises(E.InsufficientPrivilege):
                with conn.transaction():                 # even for the superuser running plain SQL
                    conn.execute(stmt)

    def test_audit_log_privacy_and_no_api_writes(self, conn, w):
        add_report(conn, w.branch["NDL"], "2026-10-01", 100)
        with as_user(conn, w.owner):
            assert one(conn, "select count(*) from public.audit_log") >= 1
        for uid in (w.owner, w.main):
            with pytest.raises(E.InsufficientPrivilege):
                with as_user(conn, uid):
                    conn.execute("insert into public.audit_log (action, table_name) values ('INSERT','x')")

    def test_cheque_changes_are_audited(self, conn, w):
        with as_user(conn, w.owner):
            aid = one(conn, "select public.create_rental_agreement(%s,'L','U','2026-10-01','2027-09-30',1000,%s::jsonb)",
                      [w.branch["ALSAFA MAIN"], json.dumps(cheques(1, 1000))])
            cid = one(conn, "select id from public.pdc_cheques where agreement_id=%s", [aid])
            conn.execute("update public.pdc_cheques set status='Cleared' where id=%s", [cid])
        acts = [r[0] for r in q(conn, "select action from public.audit_log where table_name='pdc_cheques' and record_id=%s order by id", [str(cid)])]
        assert acts == ["INSERT", "UPDATE"]


# ---------------------------------------------------------------- 18. balance calculation verification (golden case)
def golden(conn, w):
    """Hand-computed fixture (invented TEST data). Working is in docs/database/TEST_RESULTS.md and the comments below."""
    B = w.branch
    conn.execute("insert into public.opening_balances (as_of_date, receipts_bank, enbd_balance, adcb_balance, pos_pending, savings_brought_forward) "
                 "values ('2026-09-30','ENBD',10000,5000,700,300)")
    conn.execute("insert into public.opening_branch_cash (branch_id, amount) values (%s,1000),(%s,500)",
                 [B["ALSAFA MAIN"], B["JERNAS"]])
    add_report(conn, B["ALSAFA MAIN"], "2026-09-30", 999, cash=999)                                   # before start: ignored
    add_report(conn, B["ALSAFA MAIN"], "2026-10-01", 1000, cash=400, pos=300, tr=200, link=100, exp=150, sav=50)
    add_report(conn, B["JERNAS"],      "2026-10-01", 500,  cash=100, pos=100, exp=40)                 # diff 300
    add_report(conn, B["ALSAFA MAIN"], "2026-10-02", 800,  cash=500, pos=200, tr=100, exp=100, sav=20)
    cat = lambda n: one(conn, "select id from public.expense_categories where name=%s", [n])
    ins = ("insert into public.head_office_expenses (expense_date, category_id, amount, paid_from, is_saving) "
           "values (%s,%s,%s,%s,%s) returning id")
    one(conn, ins, ["2026-10-01", cat("Utilities"), 60, "Cash received", False])
    one(conn, ins, ["2026-10-02", cat("Rent"), 200, "ENBD", False])
    one(conn, ins, ["2026-10-02", cat("Repairs"), 80, "ADCB", True])
    one(conn, ins, ["2026-09-30", cat("Rent"), 5000, "Cash received", False])                        # before start: ignored
    vid = one(conn, ins, ["2026-10-02", cat("Rent"), 999, "Cash received", False])
    with as_user(conn, w.owner):
        conn.execute("select public.void_head_office_expense(%s, 'test void')", [vid])                 # voided: ignored
        ra = one(conn, "select public.create_rental_agreement(%s,'Landlord','U','2026-10-01','2027-09-30',900,%s::jsonb)",
                 [B["ALSAFA MAIN"], json.dumps([
                     {"cheque_no": "A", "bank": "ENBD", "cheque_date": "2026-10-02", "amount": 300},
                     {"cheque_no": "B", "bank": "ADCB", "cheque_date": "2026-10-02", "amount": 120},
                     {"cheque_no": "C", "bank": "ENBD", "cheque_date": "2026-10-01", "amount": 50},
                     {"cheque_no": "D", "bank": "ADCB", "cheque_date": "2026-10-20", "amount": 77},
                     {"cheque_no": "E", "bank": "ENBD", "cheque_date": "2026-11-01", "amount": 353}])])
    conn.execute("update public.pdc_cheques set status='Cleared' where agreement_id=%s and cheque_no in ('A','B','D')", [ra])


class Test18Balances:
    def test_golden_balances_at_2026_10_02(self, conn, w):
        golden(conn, w)
        with as_user(conn, w.owner):
            r = q(conn, "select * from public.app_balances('2026-10-02')")[0]
        start, asof, cash, enbd, adcb, total, sav, pos = r
        assert str(start) == "2026-10-01" and str(asof) == "2026-10-02"
        assert cash == 2150     # 1500 opening + 1000 cash received - 290 shop expenses (incl savings) - 60 HO cash
        assert enbd == 9900     # 10000 + 400 bank transfers/links (ENBD receives; POS stays pending, 0012) - 200 HO - 300 cheque A
        assert adcb == 4800     # 5000 + 0 - 80 HO - 120 cleared cheque B  (cheque D is dated 20 Oct: not yet)
        assert total == 16850   # cash + bank; unsettled POS is excluded
        assert sav == 450       # 300 b/f + 70 shop savings + 80 HO saving
        assert pos == 1300      # 700 opening + 600 POS collections - 0 settlements

    def test_cheque_counts_on_its_date(self, conn, w):
        golden(conn, w)
        with as_user(conn, w.owner):
            r = q(conn, "select adcb_now, enbd_now from public.app_balances('2026-10-20')")[0]
        assert r == (4800 - 77, 9900)

    def test_before_tracking_start_returns_opening_position(self, conn, w):
        golden(conn, w)
        with as_user(conn, w.owner):
            r = q(conn, "select cash_now, enbd_now, adcb_now, savings_total from public.app_balances('2026-09-30')")[0]
        assert r == (1500, 10000, 5000, 300)

    def test_receiving_bank_adcb_routes_receipts(self, conn, w):
        golden(conn, w)
        conn.execute("update public.opening_balances set receipts_bank='ADCB'")
        with as_user(conn, w.owner):
            enbd, adcb = q(conn, "select enbd_now, adcb_now from public.app_balances('2026-10-02')")[0]
        assert enbd == 10000 - 200 - 300 and adcb == 5000 + 400 - 80 - 120  # only bank transfers/links; POS pending

    def test_reconciliation_view(self, conn, w):
        golden(conn, w)
        rows = q(conn, "select b.name, r.report_date::text, r.total_received, r.difference, r.check_label "
                       "from public.v_daily_reports_reconciled r join public.branches b on b.id=r.branch_id "
                       "where r.report_date >= '2026-10-01' order by r.report_date, b.sort_order")
        assert rows == [("ALSAFA MAIN", "2026-10-01", 1000, 0, "Matches"),
                        ("JERNAS", "2026-10-01", 200, 300, "Diff"),
                        ("ALSAFA MAIN", "2026-10-02", 800, 0, "Matches")]

    def test_missing_reports(self, conn, w):
        golden(conn, w)
        with as_user(conn, w.owner):
            names = [r[1] for r in q(conn, "select * from public.missing_report_branches('2026-10-02')")]
            assert len(names) == 9 and "ALSAFA MAIN" not in names
            assert one(conn, "select public.missing_report_count('2026-10-01','2026-10-02')") == 2 * 10 - 3

    def test_balances_error_when_opening_missing_and_owner_only(self, conn, w):
        with pytest.raises(E.Error):
            with as_user(conn, w.owner):
                conn.execute("select * from public.app_balances()")
        conn.execute("insert into public.opening_balances (as_of_date, receipts_bank) values ('2026-09-30','ENBD')")
        with pytest.raises(E.InsufficientPrivilege):
            with as_user(conn, w.main):
                conn.execute("select * from public.app_balances()")
