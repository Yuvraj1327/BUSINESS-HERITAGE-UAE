# DEVELOPMENT_ROADMAP — ALSAFA Heritage Laundry ERP

Dependency chain: 1 → 2 → 3 → 4 → 5 → 6 → 7 → (8 ∥ 9 ∥ 10) → 11 → 12. Step 13 optional, only after scope approval (D12).
Cross-step couplings: the Step 7 dashboard uses an **alert and widget registry**; Steps 8, 9, 10 register their KPIs/alerts into it. Step 10's cheque clearing needs Step 8's balance engine (so 10 follows 8). RLS policies are designed in Step 2, applied from Step 4, and tested in Step 5 (again in 12). Global rule for every step: inspect existing project first; implement only the current step; do not break earlier work; test; fix; summarise.

## Step 1 — Requirements and Architecture
- Scope: these nine documents. Deps: none. Deliverables: docs/architecture/*. Tests: documents cross-checked against both PDFs. Acceptance: open decisions D1–D6, D12 answered or explicitly deferred; missing quotation/SQL/prototype supplied. Must not: any code, SQL, files outside docs.

## Step 2 — Database Schema and RLS
- Scope: final table, constraint, index and RLS design reconciled to `alsafa_supabase_schema.sql`; audit/void design; calculation function specs. Deps: 1, D1, D4, D5. Deliverables: finalized DATABASE_DESIGN, policy table, calculation spec. Tests: design review against golden cases. Acceptance: every table has columns, constraints, indexes, RLS rules. Must not: run SQL or create migrations in Supabase.

## Step 3 — React and FastAPI Project Setup
- Scope: repo structure, Vite+TS+Tailwind+shadcn, FastAPI skeleton, config/env, linting, test runners, CI, GitHub, deployment targets (D3). Deps: 1. Tests: build, lint, unit smoke tests, health endpoint. Acceptance: clean clone runs; no secrets in git. Must not: auth, business modules, DB tables.

## Step 4 — Supabase Integration and Authentication
- Scope: Supabase projects (dev/staging), Alembic baseline creating Step 2 schema and RLS, restricted DB role + claims mechanism, JWT verification, login/logout, /auth/me, owner account, MFA setup. Deps: 2, 3. Tests: token validity cases, anon rejected, migration up/down. Acceptance: owner logs in; invalid/expired tokens rejected; service-role key only in backend. Must not: module pages, role UI.

## Step 5 — Roles and Permissions
- Scope: Owner/Branch roles, branch assignment, backend dependencies, route guards, user management API/UI minimal, RLS test suite. Deps: 4. Tests: full ROLE_PERMISSION_MATRIX at API and DB level. Acceptance: branch user cannot reach other branches or owner data by any route. Must not: finance/employee features.

## Step 6 — Main Layout and UI
- Scope: AppShell, owner and branch layouts, navigation, responsive behaviour, design tokens, shared components and states. Deps: 3 (5 for guards). Tests: component tests, responsive checks. Acceptance: layouts work at desktop/tablet/phone. Must not: real data pages.

## Step 7 — Dashboard and Branch Reporting
- Scope: daily report submit/history, reconciliation, Branch & date view, owner dashboard (report-derived KPIs), branch dashboard, missing-report alerts, alert/widget registry, branch management basics. Deps: 5, 6. Tests: golden reconciliation cases, validation rules, duplicate prevention, branch scoping. Acceptance: all report rules enforced; Matches/Diff correct; head-office and cash widgets show as pending until Step 8. Must not: cash/bank board logic, expenses, other alerts.

## Step 8 — Finance Management
- Scope: opening balances, cash & banks, balance engine, head office expenses, savings flag, suppliers (per D5), dashboard financial KPIs and cash board. Deps: 7, D1, D5, D18–D21. Tests: hand-computed balance cases, parity with `app_balances()` [VERIFY], start-date boundary. Acceptance: cash/bank/savings match golden cases; atomic opening save. Must not: cheque features (balance hook only).

## Step 9 — Employees and Compliance
- Scope: employees, salary info, leave, visa/passport expiry and statuses, trade licences, related alerts. Deps: 7 (registry), 5. Tests: leave boundary dates, 6-calendar-month rule, colour thresholds, owner-only privacy. Acceptance: all compliance rules and cards correct. Must not: rentals, payroll processing.

## Step 10 — Rentals and Task Management
- Scope: rental agreements, atomic cheque schedule, renew, cheque statuses (clear/bounce/date change), cleared-cheque effect on banks, tasks and assignment, overdue alerts. Deps: 8, 9 (registry). Tests: split and rounding cases, month arithmetic, renew, atomicity. Acceptance: schedule totals equal rent; balances respond to cleared cheques. Must not: reports/exports.

## Step 11 — Reports and Analytics
- Scope: agreed report catalogue (D15), daily/monthly, branch comparison, financial summaries, Recharts charts, Excel and PDF exports. Deps: 7–10. Tests: totals reconcile to dashboard; export contents and permissions. Acceptance: exports open and match screens. Must not: new business rules.

## Step 12 — Testing, Security and Deployment
- Scope: full regression (frontend, backend, DB, RLS), financial verification, responsive/device testing, security review, deployment to Vercel/Render/Supabase production, backups, restore test, monitoring, runbook. Deps: all. Acceptance: all suites pass; restore tested; MFA on; sample data absent from production. Must not: new features.

## Step 13 — Optional Customer Orders and Delivery (not approved)
- Scope per PROJECT_REQUIREMENTS §23. Deps: 5, 6, shared export/audit; release after 12. Acceptance: separate module; no core table changes; reconciliation to daily sales optional. Must not start before explicit approval.

## Requirement coverage checklist

| Requirement / quotation module | Step(s) |
|---|---|
| 1 Authentication & User Mgmt | 4, 5 |
| 2 Owner Dashboard | 7 (+8, 9, 10 widgets) |
| 3 Branch Dashboard | 7 |
| 4 Branch Management | 7 (basic), 5 (assignment) |
| 5 Branch & Date View | 7 |
| 6 Daily Sales Reporting | 7 |
| 7 Sales Reconciliation | 7 |
| 8 Cash & Bank Management | 8 |
| 9 Opening Balances | 8 |
| 10 Expenses (branch/head office) | 7 (shop, via reports), 8 (head office) |
| 11 Savings | 7 (shop), 8 (total) |
| 12 Supplier Management | 8 |
| 13 Employee Management | 9 |
| 14 Salary & Leave | 9 |
| 15 Visa & Passport | 9 |
| 16 Trade Licences | 9 |
| 17 Rental Agreements | 10 |
| 18 PDC Cheques | 10 (bank effect 8 hook) |
| 19 Task Management | 10 |
| 20 Reports & Analytics, exports | 11 |
| 21 Alerts & Notifications | 7 (registry, missing reports), 9, 10, 8 (suppliers) |
| 22 Settings & Audit Logs | 5 (users), 4–12 (audit written as features land), 11 (viewer) |
| Security, RLS, backups | 2, 4, 5, 12 |
| Optional orders | 13 |

Each requirement has one owning step; audit logging is a shared utility built in Step 4 and used by later steps (no duplicated implementation).
Gaps: quotation not available, so coverage is against the brief's 14 modules; re-check after the quotation is supplied.
