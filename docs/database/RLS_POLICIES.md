# RLS_POLICIES — Step 2

Verified by `database/tests/test_database.py` on PostgreSQL 16.15 using a stub of Supabase's `auth` schema (see TEST_RESULTS.md). Not yet verified on a real Supabase project.

## Model
- Default deny. RLS enabled on all 14 public tables. `anon`: no privileges, no policies. Privileges are revoked from PUBLIC/anon/authenticated first, then re-granted minimally (Supabase's default grants are neutralised, and the test suite imitates them to prove it).
- Identity comes only from `auth.uid()`. Role and branch come from the `profiles` row via SECURITY DEFINER helpers (`app.user_role()`, `app.branch_id()`, `app.is_owner()`) with a fixed `search_path`; helpers return nothing for inactive or missing profiles. Frontend-supplied role/branch is never trusted. Helpers bypass profiles RLS, so no recursion.
- Backend connection (Step 4): log in as role `app_api` (NOLOGIN until an operator sets a password; NOINHERIT, NOBYPASSRLS), then per request `SET LOCAL ROLE authenticated` and set `request.jwt.claims` so every policy applies. The service-role key is for admin tasks only and stays on the backend.
- `app` schema is private (USAGE only for authenticated; not exposed via the Supabase API).

## Policy matrix (Owner = O, Branch User = B)

| Table | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| branches | O all; B own branch | — (the 10 are seeded) | O (name, sort_order, is_active) | none |
| expense_categories | any active user | — | — | none |
| profiles | O all; B own row | O | O (B cannot change own role/branch: no policy) | none |
| opening_balances, opening_branch_cash | O | O | O | none |
| daily_reports | O all; B own branch | O (any branch); B own branch only, created_by = self, not pre-voided | **none** (void via function) | none |
| head_office_expenses | O | O | O, **column is_saving only** | none |
| suppliers, employees, trade_licenses, rental_agreements, pdc_cheques | O | O | O | none |
| tasks | O | O | O | O |
| audit_log | O | none (definer trigger only) | none | none |
| v_daily_reports_reconciled | follows daily_reports | — | — | — |

Function execution: authenticated only (anon and PUBLIC revoked). `app_balances`, `missing_report_count`, void functions and rental functions additionally check `app.is_owner()` and raise `insufficient_privilege` otherwise.

## Protections
- Privilege escalation: branch users have no UPDATE policy on profiles and cannot insert profiles (tested: role and branch unchanged).
- Last-owner lock-out trigger.
- Inactive account: helpers return null, so all branch-scoped access disappears (tested).
- Audit tamper-protection: UPDATE/DELETE/TRUNCATE on audit_log raise even for superusers using plain SQL; writes come only from the SECURITY DEFINER trigger.

## Known limits
- `service_role` and the database owner bypass RLS by design; protect those credentials.
- Super-user-level DDL (disabling triggers) is outside what SQL policies can prevent; rely on access control and backups.
- Per-branch visibility of cash/tasks (D10, D11) is deliberately closed pending decisions.
