# Step 7 — Dashboard, Daily Reports & Branch-wise Reporting

Scope: Owner Dashboard, Daily Reports, Branch & Date View, their calculations and missing-report detection.
Cash & Banks, Opening Balances, Expenses, Suppliers, Employees, Rentals and PDC workflows are **not** built; their tables/functions are only read.

## Calculations (one place: `backend/app/core/calculations.py`)
| Figure | Rule |
|---|---|
| Total Collections | Cash + POS + Bank Transfers + Payment Links |
| Difference / Not Yet Received | Total Sales − Total Collections (can be negative); `check` = "Matches" when 0, else "Diff" |
| Shop Expenses excl. Savings | Shop Expenses − Shop Savings |
| Head Office excl. Savings | Head Office total − Head Office savings |
| Total Savings | Shop savings + Head Office savings |
| Sales Minus Expenses | Total Sales − Shop excl. savings − Head Office excl. savings |

All amounts are `Decimal`, rounded half-up to 2 places, serialised as strings (`"950.00"`). The frontend only formats them.

## API (all under `/api/v1`, JWT required, errors use the standard envelope)
| Method & path | Who | Notes |
|---|---|---|
| `POST /daily-reports` | Owner (chooses `branch_id`), Branch User (own branch; a different `branch_id` → 403) | 201. `report_date` defaults to Dubai today; future → 422; sales must be > 0; amounts ≥ 0, ≤ 2 decimals; savings ≤ shop expenses; unknown fields rejected; duplicate branch+date → 409 `duplicate_report` |
| `GET /daily-reports` | Owner all/one branch; Branch User own | `branch_id`, `date_from`, `date_to`, `page`, `page_size` (default 25, max 100); latest first |
| `GET /daily-reports/{id}` | as above | other branches look like "not found"/403 |
| `GET /daily-reports/missing` | as above | `date_from`, `date_to?`, `branch_id?` |
| `POST /daily-reports/{id}/void` | Owner only (`daily_reports:update`) | body `{reason}` (3–500 chars); 204; audited |
| `GET /dashboard/owner` | Owner only (all-branches scope; Branch User → 403, audited) | `mode=day&date=` or `mode=month&month=YYYY-MM`; future periods → 422 |
| `GET /branch-date-view` | Owner all/one; Branch User own | `date_from`, `date_to`, `branch_id?`; max 92 days; `date_to` not in future; head-office fields are `null` unless the caller may read expenses |

Branch isolation is applied twice: `BranchScope` in the API and RLS in PostgreSQL (the API connects as `authenticated` under the caller's JWT). Duplicates are blocked by the partial unique index `dr_branch_date_active_uq` and by the API (409).

## Missing-report rules
* Reporting start = `opening_balances.as_of_date + 1` (exposed to all active users via `public.reporting_start_date()`, migration 0011).
* **Start not configured → status `not_configured`**: nothing is counted and the UI says so (no misleading "0 missing"). Same for balances.
* Dates before the start are never counted (`before_start`); future days are never counted; days between start and today (Dubai) are.
* Expected = days × active branches (10 configured branches). Monthly view reports counts up to today.

## Frontend
Pages: `pages/dashboard/OwnerDashboard.tsx`, `BranchDashboard.tsx`, `pages/reports/DailyReportsPage.tsx` + `ReportForm.tsx`, `pages/branch-date/BranchDateViewPage.tsx`; shared `components/reporting/*`. Data via TanStack Query (`hooks/use-reports.ts`); submit/void invalidate `daily-reports`, `dashboard`, `branch-date-view`. Owner dashboard period is kept in the URL (`?view=month&month=2026-11`). Navigation: Branch & Date View now `live` for Branch Users (own branch only).

## Decisions and open dependencies (recorded, not silently assumed)
* **D1 – reporting start date** is unset until opening balances are saved (a later step). Until then missing-report counts and balances show "not configured".
* **D4 – corrections**: no edit/delete workflow was invented. Reports are immutable; the only correction is the existing audited Owner void (`public.void_daily_report`), which frees the date for a fresh report. Branch Users cannot void. Pending the owner's confirmation of this process.
* **D13 – SALES TEAM / holidays**: all active branches are expected to report every day; no holiday calendar exists yet.
* Head-office expenses tagged "All branches" are included in dashboard totals but are not attributed to any single branch row (shown as a separate note). A single-branch view shows only that branch's head-office spending.
* `/dashboard/branch` (branch-wise dashboard data) was not added as a separate endpoint: branch figures are inside `/dashboard/owner` (`branches`) and `/branch-date-view`.
* Alerts are built only from data that exists (visas, passports, licences, rentals, cheques, tasks, suppliers owed); empty ones are omitted.
* The dashboard Cash/Bank figures use the existing owner-only `app_balances()` function and are shown only when opening balances exist and the period is on/after the start.
* Ranges: dashboard/view inputs reject future dates; Branch & Date View limits ranges to 92 days.

## Verification
Backend 276 passed (ruff, mypy clean); database suite 152 passed; frontend 137 tests, `tsc`, eslint, prettier, production build clean; E2E 55/55 (real FastAPI + PostgreSQL + RLS). **Authentication in E2E is simulated** — a real Supabase project has not been tested.

## Deviations from `API_SPECIFICATION.md` (to be reconciled)
* Spec says a Branch User's `branch` is "ignored" on submit; Step 7 requires that another branch in the payload cannot be used, so it is **refused (403, audited)** rather than silently replaced. Omitting it uses the profile branch.
* Spec lists `/daily-reports/missing` as owner-only; it is available to Branch Users for their own branch (needed for the Branch & Date View).
