# OPEN_DECISIONS — ALSAFA Heritage Laundry ERP

Status: Step 1 planning. Nothing here has been decided by the client unless marked **DECIDED**.
Legend: **[BLOCKING]** = must be answered before the step named; **[VERIFY]** = depends on a file not yet seen.

## 0. Reference files inspected

| File | Status |
|---|---|
| ALSAFA Heritage Laundry – Technical Summary and Supabase Plan.pdf (10 pages) | Inspected in full |
| Laundry_Dashboard_Layout_for_Adit.pdf (4 pages) | Inspected in full |
| Original project quotation / requirements | **MISSING** — not in workspace. Module scope taken from the project brief's 14-module list. Every requirement needs cross-check against the quotation. |
| `alsafa_supabase_schema.sql` (companion to Technical Summary) | **MISSING** — column definitions, checks, indexes, RLS policies and the `app_balances()` function are unseen. Table contents in DATABASE_DESIGN.md come from the PDF's section 7 table only. |
| Prototype HTML (59 KB single file) | **MISSING** — the real source of business logic. Calculations were taken from the PDF's section 4 text. |

Action for client/owner: supply the three missing items into `docs/reference/`.

## 1. Blocking decisions

| ID | Decision | Why it matters | Needed before |
|---|---|---|---|
| D1 | Opening date: PDF says user wrote "30 August" but prototype uses 30 September 2026 (tracking starts 1 Oct). Which? | Every balance depends on the start date. | Step 8 (design lock in Step 2) |
| D2 | Branch logins in v1, or Owner-only first (PDF "Phase 1") then branch users (PDF "Phase 2")? Project brief treats branch users as in scope. | Affects Step 4/5 sequencing and testing scope. | Step 4 |
| D3 | Hosting. Deployment stack named as Vercel (frontend), Render (backend), Supabase. Confirm plans and regions (Render free instances sleep when idle; latency to UAE; Supabase Pro needed for backups). | Cost, cold starts, backups. | Step 3 |
| D4 | Corrections policy. Prototype cannot edit/delete wrong reports, expenses, licences, agreements. Allow owner-only edit/void with mandatory reason and audit log? Applies to daily reports too? | Schema (void columns), permissions, audit. | Step 2 |
| D5 | Supplier balances: keep single `amount_owed` with "Mark paid → 0" (destroys history) or add a bill/payment ledger? | Adds a table and changes Suppliers/Cash logic. | Step 2 |
| D12 | Optional Customer Orders & Delivery module (second PDF): approved, deferred, or rejected? | Scope, quotation, budget. | Before Step 13; default = deferred |

## 2. Assumptions stated in the Technical Summary (client must confirm — D6)

- Shop expenses are paid from branch cash.
- Rent cheques reduce the bank balance on the cheque date.
- POS, bank transfers and link payments all go to one bank (`receipts_bank`, ENBD or ADCB).
- People on leave are not paid (payroll KPI counts active staff only).
- "6 months" for the visa leave limit means calendar months.

## 3. Other open decisions

| ID | Decision | Notes |
|---|---|---|
| D7 | "Clear sample reports, expenses and balances" button | PDF says remove or owner-only with confirmation. Recommendation: remove from production; sample-data reset only in non-production environments. |
| D8 | Visa permanent-cancellation flag: persist on status change, or by scheduled job at limit date? | Rule: after leave_start + 6 calendar months visa shows cancelled; returning after limit sets it permanently cancelled. |
| D9 | Keep leave history and licence-renewal history? | Prototype overwrites (leave_start, expiry +1 year). |
| D10 | May a branch user see their own branch cash in hand / balances? | PDF: branch role sees only own daily reports. |
| D11 | Do branch users see tasks assigned to them? | PDF: branch role has no access to other tables. Brief: owner creates/assigns tasks. |
| D13 | Missing-report rules for closed days/holidays; must SALES TEAM report daily? | Month mode = days so far × 10 branches − reports received. A report requires sales > 0, so a closed day can never be submitted. |
| D14 | Employees and suppliers: CSV import only, or add/edit forms? | Prototype has no add forms. Brief implies forms. |
| D15 | Export catalogue and formats (Excel/PDF/CSV); display AED whole dirhams vs 2 decimals | Prototype has no exports. Storage will be numeric(14,2). |
| D16 | Branch and expense-category management: which fields editable? | Brief: do not invent branches. Proposal: seed 10; owner may edit name, sort order, active flag only. |
| D17 | Document uploads (licence scans, etc.) via Supabase Storage | In stack list but no PDF requirement. Default: not in v1. |
| D18 | Per-branch cash balance definition | PDF computes cash only in aggregate; head-office items with branch "All" cannot be attributed. |
| D19 | "POS settlements pending" behaviour | Shown as a card and an opening figure, but POS is credited to the bank immediately in the formula. How does the pending figure move? |
| D20 | Cash↔bank movements (deposits, withdrawals) | Not modelled in the PDF. Needed for accurate balances? |
| D21 | Savings pool: any withdrawals/use of savings? | Savings are removed from cash but never reduced. |
| D22 | Task model details: statuses (0/1/2), assignee, whether branch tasks are visible to branch users | PDF: new tasks "Unassigned". |
| D23 | Audit-log scope and retention; MFA for owner (PDF recommends) | Proposal in SYSTEM_ARCHITECTURE.md. |
| D24 | Dark theme | Prototype has light and dark; brief says light default. Proposal: light only in v1. |
| D25 | Notifications | PDF has an on-screen "Needs attention" list only. Email/WhatsApp/push notifications are not specified. Proposal: on-screen only in v1. |
| D26 | Currency formatting and rounding display | Prototype shows whole AED. |

## 4. Conflicting assumptions between sources

| Topic | Source A | Source B |
|---|---|---|
| Branch users in v1 | Brief: in scope | Technical Summary: optional Phase 2 |
| Data access | Technical Summary: browser → Supabase with anon key | Brief/stack: FastAPI backend. Resolution proposed: browser → FastAPI only. |
| Exports | Technical Summary: none exist | Brief + second PDF: Excel/CSV/PDF exports required |
| Roles | Brief: Owner + Branch User | Second PDF: Admin, Operations, Delivery, Finance |
| Expense categories | Core: 7 fixed (Detergent & chemicals, Utilities, Rent, Repairs, Transport, Packaging, Salaries) | Second PDF: Fuel, Salaries, Rent, Utilities, Packaging, Marketing, Vehicle, Maintenance, Outsourcing, Refunds, Other (editable) |
| Order statuses | Second PDF text: New > Scheduled > Picked Up > Processing > Ready > Out for Delivery > Delivered/Cancelled | Second PDF dashboard pipeline: New/Pending, Picked Up, Processing, Ready for Delivery, Delivered |
| Revenue truth | Core: daily_reports totals typed by branch | Optional: per-order payments |

## 5. Requirements that cannot be fully specified from available documents

- Exact column types, constraints, indexes and RLS policies (SQL file unseen).
- Export and report catalogue (no source defines it).
- Quotation-only scope items (quotation unseen).
- Notification channels beyond on-screen alerts.
- Anything in the prototype's UI that is not described in the Technical Summary text.

## 6. Illustrative data warning

All names, amounts, cheque numbers, landlords and balances in the Technical Summary come from a random generator. All figures in the second PDF (e.g. 284 orders, AED 29,840) are labelled "Illustrative sample data". None may be loaded as real data. Use only as test-fixture shapes.
