# Step 8 — Finance Management: Opening Balances, Cash & Banks, Expenses & Savings, Suppliers

Scope: Opening Balances, Cash & Banks, Head Office expenses and savings, Suppliers and their payments.
**Not built** (later steps): Employees, Salaries, Visas, Passports, Trade Licenses, Rental Agreements, PDC Cheques, Tasks.
The ledger already has a slot for cleared rental cheques (see "Rental cheques"), but no cheque management exists.

> Verification status: everything below was verified against a real PostgreSQL 16 with RLS, the real FastAPI app and the real React app.
> **Supabase Auth was simulated** (`e2e/fake_gotrue.py`). A real Supabase project was never available, so email delivery,
> dashboard settings and key handling on a real project are untested.

## 1. Design in one paragraph
There is **one source of truth for money: the SQL function `app_cash_bank_ledger(from, to)`**. It returns signed rows per account
(`Cash`, `ENBD`, `ADCB`, `POS Pending`) derived *without copying* from: daily reports, head-office expenses, supplier payments,
cash transfers, POS settlements and cleared rental cheques. `app_balances()`, `app_branch_cash()` and every Cash & Banks screen sum from it,
so `closing = opening + incoming − outgoing` holds by construction, nothing stores a balance that could be overwritten, and a daily-report
amount appears exactly once. The Step 7 dashboard calls the same `app_balances()` (signature unchanged), so both screens always agree.

## 2. Calculation rules
| Figure | Rule |
|---|---|
| Cash in Hand (per branch) | opening branch cash + daily-report cash received − shop expenses (**including** shop savings) − head-office cash expenses tagged to the branch |
| Cash in Hand (total) | sum of all branch rows + the "Head office / all branches" row (untagged head-office cash expenses) |
| ENBD / ADCB | opening + bank receipts attributed to the bank − head-office expenses and supplier payments paid from it − cleared rental cheques ± transfers ± POS settlements |
| Bank receipts | `bank_transfer + link_payment` of daily reports, credited to **`opening_balances.receipts_bank`** (the approved bank attribution) |
| POS Pending | opening + daily-report POS amounts − POS settlements |
| Total Cash + Bank | Cash + ENBD + ADCB. **Unsettled POS is excluded** until it is settled into a bank |
| Total Savings | savings brought forward + shop savings + head-office savings (non-voided) |
| Expenses excl. savings | total − savings (shop and head office) |
| Supplier outstanding | opening outstanding + new dues − recorded payments (voided entries never count) |
| Tracking start | `opening_balances.as_of_date + 1 day`; earlier dates are never counted |

Money is `Decimal` in the backend (2 places, half-up), `NUMERIC(14,2)` in PostgreSQL, strings on the wire. The frontend only formats (AED).
**Behaviour change vs Step 7:** POS used to be credited to the bank at the time of sale; it now sits in POS Pending until a settlement is recorded.

## 3. Database changes — `database/migrations/0012_finance_ledgers.sql` (apply once, after 0011; additive, no production data touched)
* `suppliers.notes`; unique index on `lower(btrim(name))`.
* `head_office_expenses.client_key` (idempotency) and `corrects_id` (replacement link).
* New tables: `supplier_entries` (kind `due`/`payment`), `pos_settlements`, `cash_transfers` — all with `voided_at/by/void_reason`, CHECK constraints
  (amount > 0, valid accounts, a branch exactly when cash is involved, void pair), unique partial indexes on `client_key`, RLS (owner only) and audit triggers.
* `app.finance_entry_validate()` trigger: date not in the future (Dubai), opening balances must exist, date must be after the opening date.
* `app.finance_row_immutable()`: ledger rows cannot be edited except to void them. Corrections are void + new entry.
* Functions: `app_cash_bank_ledger`, replaced `app_balances` and `app_branch_cash` (same names/columns), `void_cash_transfer`, `void_pos_settlement`,
  `void_supplier_entry`, `void_head_office_expense` (SECURITY DEFINER, owner only, reason required, audited). View `v_supplier_outstanding`.
* Two bugs found by the new tests and fixed before delivery: a trigger that read a missing column on the wrong table, and a void function
  that did not notice an already-voided row (PL/pgSQL `EXECUTE` does not set `FOUND`).

## 4. API (all under `/api/v1`, JWT required, Owner only; Branch Users get 403 and an `ACCESS_DENIED` audit row)
| Area | Endpoints |
|---|---|
| Opening balances | `GET /opening-balances`, `PUT /opening-balances`, `GET /opening-balances/history` |
| Cash & Banks | `GET /cash-banks/summary`, `/accounts`, `/branches`, `/transactions` (filters: dates, account, branch, type, paging), `/transfers`, `/pos-settlements`; `POST /cash-banks/transfers`, `/pos-settlements`, `…/{id}/void` |
| Expenses | `GET /expenses/categories`, `GET/POST /expenses`, `GET/PUT /expenses/{id}`, `POST /expenses/{id}/void`, `PATCH /expenses/{id}/saving` |
| Suppliers | `GET/POST /suppliers`, `GET /suppliers/summary`, `GET/PUT /suppliers/{id}`, `GET /suppliers/{id}/entries`, `POST /suppliers/{id}/dues`, `/payments`, `/mark-paid`, `POST /suppliers/entries/{id}/void` |

Common behaviour: Pydantic v2 strict models (unknown fields rejected), money ≥ 0 (> 0 for flows), 2 decimals, Dubai dates (future → 422), explicit DB
transactions, one advisory lock (`pg_advisory_xact_lock(80801)`) around balance-affecting writes, RLS under the caller's JWT, no service-role key anywhere.
Error codes worth knowing: `opening_not_configured` 409, `insufficient_funds` 422, `negative_balance` 422, `exceeds_outstanding` 422, `nothing_outstanding` 409,
`duplicate_transaction` 409, `opening_date_locked` 409.

## 5. Rules enforced
* **Opening balances**: Owner only; all 10 branches exactly once; amounts ≥ 0; as-of date not in the future; a not-configured state until saved.
  Changing saved values **requires a reason** and is audited with old and new values (no silent reset). The as-of date is locked once any transaction exists.
  A correction that would make any balance negative on any day is refused (422 `negative_balance`) and rolled back.
* **No invalid negatives**: expenses, supplier payments, transfers and settlements check available funds first; voids and opening corrections re-check history.
  There is **no overdraft rule** (none approved).
* **Duplicates**: every create accepts a `client_key` UUID; a repeat returns 409 and changes nothing. The UI makes one key per dialog attempt.
* **Corrections**: nothing is hard-deleted. "Delete" = void with a reason. "Edit" an expense = void the original and record a linked replacement (`corrects_id`) in one transaction.
  Marking/unmarking a saving needs a reason and is audited.
* **Shop expenses** stay in the Daily Report (Step 7); there is no second shop-expense system. Head-office expenses are the only ones entered here.
* **Transfers** are one row with two ledger legs (debit and credit) that always sum to zero; allowed between Cash↔ENBD↔ADCB; a branch is required exactly when cash is involved.
* **Suppliers**: opening dues are set in Opening Balances (or on the supplier form *before* balances are configured) and are never overwritten; dues and payments are separate history rows.
  *Mark as Paid* records one payment for the full outstanding amount. No invoices or purchase orders exist.

## 6. Frontend
Pages in `frontend/src/pages/finance/`: `OpeningBalancesPage` (form, review-and-confirm dialog, history), `CashBanksPage` (6 cards, branch cash, account movements, filtered
transaction history, transfers, POS settlements), `ExpensesPage` + `ExpenseDialog`, `SuppliersPage`, `SupplierDetailPage`, `SupplierDialog`, `SupplierPayments`, `TransferForms`.
Data layer: `schemas/finance.ts` (zod), `services/finance.service.ts` (Axios), `hooks/use-finance.ts` (TanStack Query; every write invalidates finance and dashboard queries).
Shared additions: `components/common/pagination.tsx`, `components/common/reason-dialog.tsx`. Navigation entries for the four modules are now `live`; routes use the same module/action pairs as the menu.
Every screen has loading, empty, error (with retry), confirmation and success states. Branch Users see no finance links and typed URLs show Access denied without any finance request being sent.

## 7. Permissions
Owner: full access. Branch User: none of `CASH_BANKS`, `OPENING_BALANCES`, `EXPENSES`, `SUPPLIERS`. Change: `CASH_BANKS` now grants READ, **CREATE** (transfers, settlements) and **UPDATE** (void) to the Owner.

## 8. Tests (all run against real PostgreSQL / real browser)
| Suite | Result |
|---|---|
| Backend pytest (incl. `test_step8_finance_api.py`, 65 tests) | 341 passed, 1 skipped (needs `TEST_DATABASE_URL`) |
| Database suite (incl. new tables/functions, golden balances) | 155 passed |
| Frontend vitest (incl. `finance.test.tsx`, 47 tests) | 184 passed |
| ruff, mypy (61 files), tsc, eslint, prettier, `vite build` | clean |
| End-to-end (Playwright, simulated Auth) | 67/67 (12 new Step 8 scenarios incl. 390/768/1440px layout) |

Covered: opening creation/validation/date lock/audit; cash, ENBD, ADCB, POS maths (golden case, receiving-bank routing); HO expenses and savings; supplier opening, partial/full/Mark-as-Paid;
transfer debit = credit; duplicate prevention; void/restore; Owner-only and Branch User denial at API, DB (RLS) and UI; no double counting; dashboard = Cash & Banks.

## 9. Rental cheques
The ledger function already subtracts cleared rental cheques from the cheque's bank, *if* the `rental_cheques` table of the approved schema has rows with a cleared status.
No cheque screens or workflows exist; they belong to the Rental Agreements/PDC step.

## 10. Unresolved decisions (recorded, not silently invented)
1. **Transfers (D20)** are implemented as traceable debit/credit pairs but still await explicit Owner confirmation of the rule set (accounts allowed, branch for cash).
2. **Per-report receiving bank**: the schema has no bank per daily report, so *all* bank transfers/payment links go to the single configured `receipts_bank`. If ENBD and ADCB both receive money, a column on `daily_reports` is required. Nothing is guessed.
3. **No overdraft rule** is approved, so negatives are refused. Voiding a Step 7 daily report is *not* guarded against creating a negative balance (Step 7 behaviour left untouched).
4. **Untagged head-office cash expenses** reduce the "Head office / all branches" cash row (it can be negative) while funds are checked against the *total* cash; the rows always sum to Cash in Hand. Tagging an expense to a branch moves it into that branch's row.
5. **Backdated entries** are validated at the entry date and at today only, not at every day in between.
6. **Edit of an expense = void + replacement** (so history is never rewritten); the replacement is a new record id.
7. The category "Detergent & chemicals" keeps its seeded casing; the brief wrote "Detergent & Chemicals".
8. POS Pending and the cash+bank total changed meaning vs Step 7 (see section 2); confirm this is the intended accounting.
