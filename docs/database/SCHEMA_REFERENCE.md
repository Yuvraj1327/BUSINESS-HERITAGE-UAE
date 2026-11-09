# SCHEMA_REFERENCE — Step 2

Implemented in `database/migrations/0001..0009`. Verified on PostgreSQL 16.15 (local test server). Not yet applied to any Supabase project.
`alsafa_supabase_schema.sql` was NOT available: columns come from the Technical Summary (section 7 and form fields); differences from the unseen SQL are **[VERIFY]**.

Conventions: UUID primary keys (`gen_random_uuid()`), `numeric(14,2)` money, `date` business dates, `timestamptz` timestamps, "today" = Asia/Dubai, text + CHECK instead of native enums (easier Alembic evolution). `created_by` references auth users only where the PDF does (daily_reports, head_office_expenses); elsewhere it is a plain uuid. `updated_at/updated_by` are maintained by trigger.

## Tables

| Table | Key columns | Constraints / rules | Indexes |
|---|---|---|---|
| branches | id, name, sort_order, is_active | unique name; name not blank | sort_order |
| expense_categories | id, name, is_active | unique name | — |
| profiles | user_id (PK, FK auth.users), full_name, role, branch_id, is_active | role in (owner, branch); owner => no branch, branch => branch required; **last active owner cannot be demoted/deactivated/deleted** (trigger) | branch_id |
| opening_balances | id (=1), as_of_date, receipts_bank, enbd_balance, adcb_balance, pos_pending, savings_brought_forward | single row; bank in (ENBD, ADCB); amounts >= 0; not seeded | — |
| opening_branch_cash | branch_id (PK/FK), amount | amount >= 0; one row per branch | — |
| suppliers | id, name, category, payment_terms, amount_owed, is_active | owed >= 0; name not blank | is_active |
| head_office_expenses | id, expense_date, branch_id (null = All), category_id, amount, paid_from, note, is_saving, void cols | amount >= 0; paid_from in (Cash received, ENBD, ADCB); void_reason set iff voided_at set | date; (paid_from, date); branch |
| daily_reports | id, report_date, branch_id, total_sales, order_count, cash_received, pos_amount, bank_transfer, link_payment, shop_expenses, shop_savings, void cols, created_by | sales > 0; all amounts and order_count >= 0; shop_savings <= shop_expenses; **no future date (Dubai) by trigger**; **unique (branch_id, report_date) among non-voided rows** | (branch, date desc); date |
| employees | id, full_name, branch_id, role_title, monthly_salary, visa_expiry, passport_expiry, status, leave_start, visa_cancelled | status in (Active, Leave); leave_start present exactly when Leave; leave_start not future; salary >= 0; **no passport/Emirates ID numbers** | branch; status; visa_expiry; passport_expiry |
| tasks | id, title, branch_id (null = All), assignee_user_id (null = Unassigned), due_date, status | status in (To Do, In Progress, Done) | (status, due_date) |
| trade_licenses | id, branch_id, license_no, authority, expiry_date, renewal_fee | fee >= 0 | expiry_date; branch |
| rental_agreements | id, branch_id, landlord, unit, start_date, end_date, annual_rent, status, renewed_from_id | end > start; rent > 0; status in (Active, Renewed, Terminated) | branch; end_date |
| pdc_cheques | id, agreement_id, cheque_no, bank, cheque_date, amount, status, cleared_at | bank in (ENBD, ADCB); status in (Pending, Cleared, Bounced); amount > 0; unique (agreement_id, cheque_no); cleared_at maintained by trigger and required iff Cleared | (status, cheque_date); agreement |
| audit_log | id (identity), occurred_at, actor_user_id, action, table_name, record_id, old_values, new_values, reason | append-only (update/delete/truncate raise) | (table, record); occurred_at; actor |

## Functions and views

| Object | Purpose | Security |
|---|---|---|
| v_daily_reports_reconciled | total_received, difference (= not yet received), check_label Matches/Diff; excludes voided | security_invoker (RLS applies) |
| app_balances(p_as_of) | tracking_start, cash_now, enbd_now, adcb_now, total_cash_bank, savings_total, pos_pending per BUSINESS_LOGIC §5; voided rows excluded | invoker, owner only |
| missing_report_branches(date) | active branches without a non-voided report | invoker (branch user sees only own) |
| missing_report_count(from, to) | days x active branches - reports | invoker, owner only |
| void_daily_report / void_head_office_expense(id, reason) | owner correction without deleting; reason mandatory; audited | definer, fixed search_path, explicit owner check |
| create_rental_agreement(...) | agreement + 1-12 cheques atomically; cheque total must equal annual rent | invoker, owner only |
| renew_rental_agreement(id, cheques) | new start = old end + 1 day; new end = old end + 1 year; same rent and cheque count; old agreement kept and marked Renewed; cannot renew twice | invoker, owner only |
| app.user_role / branch_id / is_owner | RLS helpers reading trusted profile data | definer, fixed search_path |
| app.touch_row, dr_validate, employee_validate, pdc_before, guard_last_owner, audit_row_change, audit_immutable | triggers | see file |

## Deviations from Step 1 docs / decisions pending

1. **UUID keys** (Step 2 prompt) instead of the PDF's bigint identity.
2. **Not created (decisions pending, no rule invented):** financial ledger, cash_bank_movements (D20), supplier_payments/bills ledger (D5), leave_history and license_renewals (D9). `audit_log` records before/after values of every change meanwhile. Suppliers keep the PDF's single `amount_owed`.
3. **No hard deletes** for the owner on any table except `tasks`; daily_reports cannot be updated by anyone directly (void function only); head_office_expenses owner may only toggle `is_saving` directly. Step 1 said "protect against accidental deletion"; PDF said owner has full access. Revisit with D4.
4. **Void columns and partial unique index** on daily_reports (corrections, D4). If D4 rejects corrections, drop the void functions/columns in a later migration.
5. **sales > 0 is enforced in the database** (PDF form rule, Step 2 prompt). A closed day cannot be reported (D13).
6. **Rental renewal creates a new agreement row** (`renewed_from_id`); the PDF "replaces cheques" in place. Chosen so financial history is preserved.
7. Task status stored as text (To Do / In Progress / Done) rather than PDF 0/1/2; assignee is a user reference.
8. Alert calculations (visa, passport, licence, cheque due) are NOT in the database; backend services (Steps 9-10) compute them.
9. Rounding rule for the cheque split and month arithmetic is not fixed in SQL (backend computes, DB verifies sum) **[VERIFY]**.
10. Non-negative bank balances follow the PDF; overdrafts would be rejected (confirm).
