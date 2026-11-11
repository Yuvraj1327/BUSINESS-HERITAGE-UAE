# ROLE_PERMISSION_MATRIX — ALSAFA Heritage Laundry ERP

Roles: **Owner**, **Branch User** (assigned to exactly one branch). Anonymous users have no access to anything.
Source: Technical Summary section 6 (proposed) and project brief. The prototype has no permissions today. Approve = **N/A** (no approval workflow exists in any source; D-list item if wanted).
Legend: R read, C create, U update, D delete (see note), X export, — none. "Void" = audited soft cancel; hard delete is not permitted on financial or compliance records.

## 1. Permission matrix

| Resource | Owner | Branch User |
|---|---|---|
| Own profile | R | R (own) |
| Profiles / users | R C U (deactivate); D = —  | — |
| Branches | R, U (name, order, active) | R (own branch only) |
| Expense categories | R, U (per D16) | R |
| Daily reports | R (all), C, U/Void with reason (per D4), X | R (own branch), C (own branch, own date rules) , U —, D —, X —(D15) |
| Head office expenses | R C U/Void, saving toggle, X | — |
| Opening balances / opening branch cash | R C U, X | — |
| Cash & bank views | R, X | — (D10) |
| Suppliers (and ledger if approved) | R C U, mark paid, X | — |
| Employees (incl. salary) | R C U, status change, X | — |
| Visa / passport expiry | R U, X | — |
| Trade licences | R C U (mark renewed), X | — |
| Rental agreements | R C U (renew), X | — |
| PDC cheques | R C U (clear, bounce, replace a bounced cheque, edit while Pending), X; cleared / bounced cheques are final (Step 10) | — |
| Tasks | R C U (assign, status), X | — (D11, T1: still undecided) |
| Notifications / Alerts (Step 11) | R U (read, acknowledge) | — |
| Dashboard (owner) | R all branches | — |
| Branch dashboard | — | R own branch, built from own daily reports only |
| Branch & date view | R all | R own branch only |
| Reports & analytics | R X | — (own history only) |
| Alerts | R all | — |
| Audit log | R | — |
| Settings | R U | — |
| Approve | N/A | N/A |

Branch User restrictions (from brief and PDF): no other branches; no owner-only financial or employee information; cannot edit or delete submitted daily reports; no user management or admin access.

## 2. Responsibilities by layer

| Concern | FastAPI (backend authorization) | Database (RLS and constraints) |
|---|---|---|
| Identity | Verify Supabase JWT signature, expiry, audience; load profile, role, branch, is_active | `auth.uid()` from per-request claims |
| Role gate | Dependencies: owner-only and branch-or-owner | Owner policy: full access; branch policy: restricted tables |
| Branch scoping | Force branch_id from profile for branch users; ignore client-supplied branch | Policy `branch_id = profile.branch_id` for read/insert on daily_reports |
| No edit/delete | No PUT/PATCH/DELETE routes for branch users | No UPDATE/DELETE policy for branch role |
| Business rules | Reconciliation, date rules, atomic multi-row writes, audit entries | CHECK constraints (non-negative amounts, savings ≤ expenses, no future date, leave rules), unique (branch, date) |
| Private data | Owner-only routers for salary, visas, passports | No branch policy on employees, suppliers, balances, rentals, etc. |
| Anonymous | Reject missing/invalid token | No policies for `anon` on any table |
| Admin operations | Service-role key used only server-side for user creation | Key never in frontend |

Design rule: RLS must actually apply to API queries (restricted DB role plus per-request JWT claims). If the API used a bypass role, database-level enforcement would be silently lost.

## 3. Test obligations (Steps 5 and 12)

- For every row above, an automated test logged in as Branch User (own and other branch) and Owner, through the API and directly at DB level.
- Anonymous requests rejected everywhere.
- Deactivated profile rejected.
- Branch User cannot read salary, visa, passport, supplier, balance or rental data by any route.


## Step 8 note
`CASH_BANKS` now grants the Owner READ, CREATE (transfers, POS settlements) and UPDATE (void). `OPENING_BALANCES`, `EXPENSES`, `SUPPLIERS` and `CASH_BANKS` remain Owner-only; Branch Users have none of them.


## Step 9 note
Employees, Visas & Passports and Trade Licenses (including salaries and the compliance alert feed) are Owner only; Branch Users have no grant, get 403 from the API and Access denied in the UI. RLS on `employees`, `trade_licenses` and `license_renewals` is owner-only. See `docs/hr/STEP9_EMPLOYEES_COMPLIANCE.md` section 10.
