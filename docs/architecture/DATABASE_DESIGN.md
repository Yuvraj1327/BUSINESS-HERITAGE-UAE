# DATABASE_DESIGN — ALSAFA Heritage Laundry ERP

No SQL in this document. Source for the 13 core tables: Technical Summary section 7 (key columns only) and section 3 (form fields). `alsafa_supabase_schema.sql` was **not available** — full column lists, check definitions, indexes and RLS policies must be reconciled against it before Step 2 is signed off **[VERIFY]**. Items marked *(proposed)* are additions or inferences, not from the PDF.

## 1. Global conventions

- Amounts numeric(14,2); dates are `date`; identity keys bigint; "today" in Asia/Dubai.
- Audit columns on every table *(proposed)*: created_at, created_by, updated_at, updated_by.
- Financial and compliance records use void columns *(proposed, D4)*: voided_at, voided_by, void_reason. No hard deletes.
- Only the owner modifies anything except daily_reports inserts by branch users.
- Calculated, not stored (PDF): reconciliation difference, total received, all balances and cash board figures, visa/passport statuses, days on leave, alerts, KPIs.

## 2. Core tables (from PDF)

### branches
Purpose: the 10 branches. Columns: id, name (unique), sort_order, is_active. Seed exactly: ALSAFA MAIN, JERNAS, SATWA, BURDUBAI, NDL, AL BARSHA, MIRDIF, AL JADDAF, KARAMA, SALES TEAM. Referenced by most tables. RLS: owner all; branch user read own.

### expense_categories
Purpose: fixed 7 categories. Columns: id, name (unique). Values: Detergent & chemicals, Utilities, Rent, Repairs, Transport, Packaging, Salaries. RLS: authenticated read; owner write.

### profiles
Purpose: login users and roles. Columns: user_id (PK/FK auth user), full_name, role (owner|branch), branch_id (FK branches), is_active. Check: owner has no branch; branch user must have one. RLS: user reads own; owner all.

### opening_balances
Purpose: single row of settings. Columns: as_of_date, receipts_bank (ENBD|ADCB), enbd_balance, adcb_balance, pos_pending, savings_brought_forward. Constraint *(proposed)*: exactly one row. Derived: start date = as_of_date + 1. RLS: owner only.

### opening_branch_cash
Purpose: opening cash per branch. Columns: branch_id (FK), amount. Unique per branch. RLS: owner only.

### daily_reports
Purpose: one report per branch per day.
Columns: id, report_date, branch_id (FK), total_sales, order_count, cash_received, pos_amount, bank_transfer, link_payment, shop_expenses, shop_savings, created_by (FK auth user).
Unique: (branch_id, report_date). Checks: amounts ≥ 0; shop_savings ≤ shop_expenses; report_date not in future (Dubai); total_sales > 0 is an app rule per PDF form rules (confirm whether a DB check, D13).
Indexes *(proposed)*: (branch_id, report_date desc), (report_date).
RLS: owner all; branch user select and insert own branch only; no update/delete for branch.

### head_office_expenses
Columns: id, expense_date, branch_id (FK, null = All), category_id (FK), amount, paid_from (Cash received|ENBD|ADCB), note, is_saving, created_by.
Checks: amount ≥ 0. Indexes *(proposed)*: (expense_date), (paid_from, expense_date). RLS: owner only.

### suppliers
Columns: id, name, category ("Supplies"), payment_terms, amount_owed, is_active. RLS: owner only. See `supplier_transactions` (D5).

### employees
Columns: id, full_name, branch_id (FK), role_title, monthly_salary, visa_expiry, passport_expiry, status (Active|Leave), leave_start, visa_cancelled.
Checks: leave_start required exactly when status = Leave. Passport/Emirates ID numbers not stored. Indexes *(proposed)*: (status), (visa_expiry), (passport_expiry). RLS: owner only.

### tasks
Columns: id, title, branch_id (FK, null = All), assignee (text in PDF), due_date, status (0 To do, 1 In progress, 2 Done). Proposed: assignee_user_id FK profiles (D22). Index *(proposed)*: (status, due_date). RLS: owner only (D11).

### trade_licenses
Columns: id, branch_id (FK), license_no, authority, expiry_date, renewal_fee. Index *(proposed)*: (expiry_date). RLS: owner only.

### rental_agreements
Columns: id, branch_id (FK), landlord, unit, start_date, end_date, annual_rent. Check: end_date > start_date. RLS: owner only.

### pdc_cheques
Columns: id, agreement_id (FK, cascade on agreement delete in PDF; with void policy use restrict *(proposed)*), cheque_no, bank (ENBD|ADCB), cheque_date, amount, status (Pending|Cleared|Bounced). Indexes *(proposed)*: (status, cheque_date), (agreement_id). RLS: owner only.

## 3. Relationship summary

branches 1—n daily_reports, head_office_expenses (optional), employees, tasks (optional), trade_licenses, rental_agreements, opening_branch_cash, profiles (branch users).
expense_categories 1—n head_office_expenses. rental_agreements 1—n pdc_cheques. auth users 1—1 profiles; auth users 1—n created_by columns.

## 4. Additional tables (justified)

| Table | Purpose | Justification | Status |
|---|---|---|---|
| audit_log | who/what/when, old and new values, reason | Required by brief; PDF recommends | Add |
| supplier_transactions | bills and payments per supplier | "Mark paid → 0" destroys history; accurate dues | **Pending D5** |
| financial_adjustments / void fields | owner-only corrections | D4; keeps balances accurate | Pending D4 (void columns planned either way) |
| leave_history | each leave period | Prototype overwrites leave_start | Pending D9 |
| license_renewals | renewal history | Prototype adds a year in place | Pending D9 |

On "financial transactions": the PDF derives balances from reports, expenses and cleared cheques rather than a ledger, so no general ledger table is planned. Balances remain computed from source records (avoid double-entry drift). Cash↔bank transfers (D20) and POS settlement (D19) would require a `cash_bank_movements` table if approved. Pending.

## 5. Financial integrity rules

- Balances computed from immutable source rows; voided rows excluded and logged.
- Duplicate prevention: unique (branch, date) for daily reports; idempotency key on create endpoints that post money *(proposed)*.
- Atomic: agreement + cheques created and renewed in one transaction; opening-balance save (balances, branch cash, supplier owed) in one transaction.
- Status changes on cheques and supplier payments write audit entries.

## 6. RLS summary

RLS enabled on every table. `anon` has no access. Owner: full access to all tables. Branch user: read own profile, branches and categories; read and insert own-branch daily_reports; nothing else. Policies and the restricted-role/claims connection model are specified in ROLE_PERMISSION_MATRIX.md.

## 7. Optional tables (Step 13 only — not approved)

customers, orders (unique order id, type Standard|Express, category, pickup/delivery timestamps, order status, payment status, amount, discount, fee, notes, updated_at), order_payments (multiple per order, method Cash|Card|Link), service_categories (editable list: Wash & Fold, Wash & Iron, Ironing, Dry Cleaning, Shoes, Curtains, Carpets, Bulky, Other), order_status_history. Must not alter core tables.

## 8. Reconciliation items against the SQL file [VERIFY]

Column names/types, defaults, exact check wording, index set, the `app_balances()` signature, policy names, seed data for branches and categories, and the field mapping given in the PDF (d→report_date, b→branch_id, sales→total_sales, orders→order_count, cash→cash_received, pos→pos_amount, tr→bank_transfer, link→link_payment, exp→shop_expenses, sav→shop_savings).
