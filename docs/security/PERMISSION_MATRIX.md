# PERMISSION_MATRIX

Source of truth in code: `backend/app/core/permissions.py` (`PERMISSION_MATRIX`). This document explains it. Default is **DENY**: anything not granted below is refused. Scope: **ALL** = every branch, **OWN** = the user's assigned branch only.

Actions: **R**ead, **C**reate, **U**pdate, **D**elete, **A**pprove, **E**xport, **M**anage.

| Module | Owner | Branch User | Notes |
|---|---|---|---|
| Dashboard | R, E · ALL | R · OWN | dashboards are built in Step 6+ |
| Branch Management | R, U, M · ALL | R · OWN | owner edits name/order/active only (D16). Branch user may read their own branch record, no management |
| Daily Reports | R, C, U, E · ALL | R, C · OWN | Owner U = audited void with reason (D4). Branch user: **no U, no D, no E**; reports are immutable to them |
| Cash & Banks | R, E · ALL | – | |
| Opening Balances | R, C, U, E · ALL | – | |
| Expenses (head office) | R, C, U, E · ALL | – | branch shop expenses are a field of the daily report, covered by Daily Reports/C |
| Suppliers | R, C, U, E · ALL | – | |
| Employees | R, C, U, E · ALL | – | salary data |
| Visas & Passports | R, U, E · ALL | – | |
| Trade Licenses | R, C, U, E · ALL | – | |
| Rentals & Cheques | R, C, U, E · ALL | – | |
| Tasks | R, C, U, D, E · ALL | – | only module with delete (schema allows it); branch access pending D11 |
| Reports (analytics) | R, E · ALL | – | branch user's "own history" = Daily Reports/R |
| User Management | R, C, U, M · ALL | – | no delete: accounts are deactivated, never removed |
| Settings | R, U, M · ALL | – | |
| Audit Log | R · ALL | – | (extra row; the architecture doc lists it Owner-read) |

"–" means no grant (DENY). **APPROVE is held by nobody**: no approval workflow exists in any source document. **DELETE** is held only for Tasks: hard deletes of financial/compliance records are not offered (schema decision D4, audited voids instead).

## Mapping to the Step 5 brief
The brief's table is implemented as written, with these interpretations (all default to the safer reading):
- "Owner: Full" = every action the design allows for that module (not DELETE or APPROVE where none is defined).
- Expenses / Branch User "Only permitted own-branch reporting" → no separate Expenses permission; own-branch shop expenses are entered inside the daily report (Daily Reports/C).
- Reports / Branch User "Own permitted reporting" → own history through Daily Reports/R; the Reports (analytics) module is denied.
- Tasks / Branch User "Only permitted assigned tasks" → denied until D11 is decided (tasks have no branch-user RLS policy).

## Unresolved permission decisions (need the owner's answer; defaults shown are what is built)
| # | Question | Built default | Where it matters |
|---|---|---|---|
| D4 | May the Owner correct (void) daily reports and expenses? | yes, audited void with reason | Daily Reports/U, Expenses/U |
| D10 | May a branch user see their own branch cash balance? | no | Cash & Banks denied |
| D11 | Do branch users see tasks assigned to them? | no | Tasks denied |
| D15 | May branch users export their own reports? Export formats? | no export for branch users | Daily Reports/E |
| P1 | Should branch users get Reports (analytics) for their own branch beyond the raw history? | no | Reports denied |
| P2 | Is an approval workflow wanted (e.g. owner approves large expenses)? | none; APPROVE unused | all modules |
| P3 | Can an Owner create other Owners in-app, or only the operator script? | script only | User Management/C |
| P4 | Can a branch user read the list of branches other than their own (e.g. for inter-branch reports)? | no, own branch only | Branch Management |
| P5 | Multi-branch managers (one user, several branches)? | not supported: exactly one branch (CHECK constraint) | role model |

## Changing the matrix
Edit `permissions.py`, update this file and the tests in `backend/tests/test_permission_matrix.py` (which pins the exact Branch User grant set), run the database tests if a policy changes, and note it in the change log. There is no runtime UI for permission changes.
