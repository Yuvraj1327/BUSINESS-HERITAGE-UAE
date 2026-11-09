# PROJECT_REQUIREMENTS — ALSAFA Heritage Laundry ERP

Sources: Technical Summary (TS) and Dashboard Layout PDF (DL) — both inspected; original quotation — **not available**; schema SQL and prototype HTML — **not available** (items marked [VERIFY]). Branches: ALSAFA MAIN, JERNAS, SATWA, BURDUBAI, NDL, AL BARSHA, MIRDIF, AL JADDAF, KARAMA, SALES TEAM. Currency AED; banks ENBD, ADCB. Module numbers follow the Step 1 list. Business formulas are in BUSINESS_LOGIC.md; permissions in ROLE_PERMISSION_MATRIX.md; tables in DATABASE_DESIGN.md.

"(new)" = required by the brief but absent from the prototype; "(TS)" = in the prototype description.

## Product-wide requirements

- Responsive on desktop, tablet, mobile browsers. Light theme default, navy/professional blue.
- Search, filters, pagination on tables; loading, empty and error states everywhere.
- Owner and Branch User experiences are separate. All permissions enforced in backend and database.
- Dates stored as dates; Asia/Dubai for "today". AED, whole dirhams display (TS) with 2-decimal storage.
- Core scope excludes the DL order module (Section 23).

## 1. Authentication and User Management

- Purpose: secure sign-in; owner creates users. Login, logout, session expiry, password reset (new), owner MFA recommended (TS).
- Owner: create/deactivate users, assign role and branch (new).
- Branch User: sign in; see own profile.
- Pages: Login; Profile; Users (owner).
- Forms — Login: email, password. User: full name, email, role (owner|branch), branch (required for branch), active.
- Table columns: name, email, role, branch, active, last sign-in.
- Validations: branch user must have a branch; owner has none; unique email.
- DB: profiles, Supabase Auth. KPIs: none.

## 2. Owner Dashboard (TS 3.1)

- Controls: Day / Whole month toggle; date picker or month picker; Previous, Next, Today/This month.
- KPI cards: Sales; Total received; Shop expenses (excl. savings); Head office expenses (excl. savings); Savings; Sales minus expenses; Orders; Cash + bank balance now.
- Cash board: cash table and bank table (columns in BUSINESS_LOGIC §5); note before start date.
- Needs attention list (11 alert types), Sales by branch bars, Day by day table (month mode only), Branch by branch table.
- DB: daily_reports, head_office_expenses, opening_*, pdc_cheques, employees, tasks, trade_licenses, rental_agreements, suppliers.

## 3. Branch Dashboard (new)

- Branch User landing page: own branch only, derived from own daily_reports: sales, total received, shop expenses (excl. savings), savings, not yet received, orders; recent submissions with Check column; missing-report reminder for today.
- Excludes head office expenses, cash/bank balances (D10).

## 4. Branch Management (new for UI; branches seeded)

- Owner: list branches, edit name, sort order, active (D16). No branch creation beyond the ten without approval.
- Columns: name, order, active, assigned users. Validation: unique name.

## 5. Branch & Date View (TS 3.2)

- Filters: Branch (All or one), From, To, quick buttons Today, Yesterday, Last 7, Last 14 days.
- Shows: Sales, Total received, Shop expenses, Head office expenses, Savings, Sales minus expenses, Not yet received; receivings split (cash, POS, bank transfers, link payment, orders); daily reports table with totals row (one branch: days without report show "Report not submitted", up to 92 days); head office expenses table with totals.
- Branch User: same view restricted to own branch (head office section hidden).

## 6. Daily Sales Reporting (TS 3.3)

- Form (10 fields): Date, Branch, Total sales, Orders, Cash received, POS machine, Bank transfers, Link payment, Shop expenses, Of which savings.
- Validations: date and sales > 0 required; savings ≤ shop expenses; no future dates; one report per branch per day (duplicates refused); no edit by branch user.
- Branch User: branch fixed to own; sees confirmation after save (Matches or difference).
- Table: latest 25 reports with Check column (Matches/Diff); history with pagination (new).
- Owner correction: audited void/edit (D4).

## 7. Sales Reconciliation

- Computed per report: total received, difference, Not yet received, Check label. Shown on save confirmation, history tables, dashboard, Branch & date view. Formulas in BUSINESS_LOGIC §2.

## 8. Cash & Bank Management (TS 3.4, owner, view only)

- Cards: Total cash + banks, Cash in hand, ENBD, ADCB, POS settlements pending, Savings (incl. brought forward).
- Opening balances table; Movements since start (latest 25): daily bank receipts, daily branch cash less shop expenses, head office expenses, cleared rent cheques.

## 9. Opening Balances (TS 3.5, owner)

- Fields: Balances as at (default 30 Sep 2026, D1), Tracking starts on (automatic, next day), POS/transfers/links go into (ENBD or ADCB), cash in hand for each of the 10 branches, ENBD balance, ADCB balance, POS settlements pending, Savings brought forward, opening amount owed to each supplier.
- Action: Save opening balances (atomic). "Clear sample data" removed from production (D7).
- Validation: amounts ≥ 0. Changing as-at date after data exists needs confirmation and audit.

## 10. Branch and Head Office Expenses (TS 3.6)

- Cards: Shop expenses (14 days), Head office from cash received, Head office from bank, All expenses (excl. savings), Savings.
- Shop expenses per branch: read-only, from daily reports.
- Add head office expense — fields: Date, For branch (All or one), Category (7 fixed), Amount, Paid from (Cash received, ENBD, ADCB), Note, Mark as saving.
- List (latest 30) with Expense and Savings columns; Mark / Unmark as saving action.
- Validation: amount > 0; date valid. Corrections per D4.

## 11. Savings Management

- Savings = shop savings (from reports) + head office items marked saving; total includes brought forward. Shown on dashboard, Cash & Banks, Expenses cards. No separate form beyond the saving flag and the opening figure. Withdrawals undefined (D21).

## 12. Supplier Management (TS 3.7)

- Cards: Total owed, Active suppliers. Table: Supplier, Supplies, Terms, Owed, Mark paid.
- New: add/edit supplier form — name, supplies (category), payment terms, amount owed, active (D14); ledger pending D5.

## 13. Employee Management (TS 3.8)

- Cards: Active, On leave, Close to 6 months, Visas cancelled, Monthly payroll (active only).
- Table: Name, Branch, Role, Status, Passport expires, On leave since, Days on leave, Visa cancels on, Salary per month, Mark on leave / Mark returned.
- New: add/edit employee — full name, branch, role title, monthly salary, visa expiry, passport expiry, status (D14).

## 14. Salary and Leave Management

- Update status form: Employee, New status (On leave or Active), Date (not in future). Leave rules in BUSINESS_LOGIC §7. Monthly payroll card. Salary is owner-only. No payslip/payroll processing is specified — not in scope.

## 15. Visa & Passport Tracking (TS 3.9)

- Cards: Visas expiring in 30 days, Passports expiring in 30 days, Passports under 6 months left.
- Update expiry form: Employee, Document (Visa or Passport), New expiry date.
- Table: Employee, Branch, Status, Visa expires, Visa status, Passport expires, Passport status, Visa cancels (leave limit). Sort cancelled first, then earliest expiry. Colour rules in BUSINESS_LOGIC §7.

## 16. Trade License Management (TS 3.10)

- Cards: Licences, Expiring within 60 days, Renewal fees due in 90 days.
- Add licence: Branch, Licence no., Authority, Expiry, Renewal fee. Table with Mark renewed (adds one year).

## 17. Rental Agreements (TS 3.11)

- Cards: Rental agreements, Total annual rent, PDCs due in 30 days, Cheques due (count), Bounced cheques.
- Add agreement: Branch, Landlord, Shop/unit, Start date, End date, Annual rent, Number of cheques (1–12), First cheque date, First cheque no., Cheques drawn on (ENBD or ADCB); one editable row per cheque (Cheque no., Bank, Cheque date, Amount) with total-versus-rent check.
- Agreements table: Branch, Landlord, Start, End, Status, Annual rent, PDCs (cleared/total), Next cheque, PDCs button, Renew button.
- Validation: end > start; cheques 1–12; cheque total = annual rent. Creation and renewal atomic.

## 18. PDC Cheque Management

- Cheques due in next 30 days list with Mark cleared.
- Inside agreement: schedule (change date of pending/bounced cheque, Mark cleared, Bounced), Add cheque (no., bank, date, amount).
- Statuses Pending, Cleared, Bounced. Cleared cheques reduce bank on cheque date.

## 19. Task Management (TS 3.12)

- Add task: New task, Branch (All or one), Due date; (new) assignee. Three columns To do, In progress, Done; buttons Start, Mark done; Overdue flag when past due and not done.

## 20. Reports & Analytics

- Prototype views: Dashboard (day/month), Branch & date view, Cash & banks movements, page KPI cards.
- New (brief, no source defines catalogue — D15): daily and monthly reports, branch comparison, financial summary, charts, Excel and PDF export. Exact report list to be agreed before Step 11.

## 21. Alerts and Notifications

- On-screen "Needs attention" with the 11 conditions (BUSINESS_LOGIC §12). Push/email/WhatsApp not specified (D25). Alert registry design allows later modules to add alerts.

## 22. Settings and Audit Logs (new)

- Settings: users, branches (limited), expense categories (D16), thresholds read-only (30/60/90/180 days from rules).
- Audit log (owner): timestamp, user, action, table, record, old/new values, reason; filter by user, date, table. Logged: financial edits, status changes (cheques, leave), user changes, opening-balance saves, voids.

## 23. Optional module — Customer Orders & Delivery (DL; NOT APPROVED — Step 13)

Kept separate. Features from DL: customer records (name, mobile/WhatsApp, address, notes); New/Edit Order with fields Order ID (auto/manual, unique), Customer Name, Mobile/WhatsApp, Customer Address, Service Category, Service Type (Standard/Express), Pickup Date & Time, Delivery Date & Time, Order Status, Payment Status, Order Amount (AED), Payment Method (Cash/Card/Link); All Orders list with search by Order ID/phone, status filter, export; Today's pickups and deliveries (by scheduled date); overdue deliveries; order pipeline; payments (order total, discounts, service fee, collected, balance, multiple payments); expense entry (date, category, amount, paid by, notes); reports with slicers (date range, category, order type, status, payment) and KPIs (orders, gross sales, collected, outstanding, AOV, express count, expenses); roles Admin/Operations/Delivery/Finance suggested; Excel/CSV export; activity log. Integration: see SYSTEM_ARCHITECTURE.md §8. DL numbers are illustrative.

## Quotation cross-check

Not performed — quotation unavailable. The 14 quotation modules are assumed to be: Dashboard, Branch Management, Daily Sales & Reporting, Cash & Bank Management, Opening Balances, Expenses & Savings, Supplier Management, Employee Management, Visas & Passports, Trade Licenses, Rental Agreements & PDC Cheques, Task Management, Reports & Analytics, User Management and Settings; each maps above (see coverage table in DEVELOPMENT_ROADMAP.md).
