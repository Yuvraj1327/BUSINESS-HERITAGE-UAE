# API_SPECIFICATION — ALSAFA Heritage Laundry ERP

Conceptual plan only; nothing is implemented. Base path `/api/v1`. All routes require a valid Supabase JWT except health. Roles: **O** = Owner, **B** = Branch User (own branch only; branch taken from profile), **O/B** = both. Responses: JSON; lists paginated (`items`, `total`, `page`, `page_size`); errors use one envelope (`code`, `message`, `fields`). Money as decimal strings; dates ISO `YYYY-MM-DD`. Validation is Pydantic, mirrored by Zod on the frontend. Mutating owner routes write audit_log. Exact payloads to be finalized in Step 2/4 against the SQL file [VERIFY].

## 1. Auth and users

| Method Path | Purpose | Role | Request | Response | Validation |
|---|---|---|---|---|---|
| GET /health | liveness | public | — | status | — |
| GET /auth/me | current profile | O/B | — | user, role, branch | active profile required |
| GET /users | list users | O | filters, page | users | — |
| POST /users | create user (service key server-side) | O | name, email, role, branch_id | user | branch required iff branch role; unique email |
| PATCH /users/{id} | edit/deactivate | O | name, branch, active | user | cannot deactivate last owner |

## 2. Branches and categories

| GET /branches | list (B: own only) | O/B | — | branches | — |
| PATCH /branches/{id} | name, order, active | O | fields | branch | unique name |
| GET /expense-categories | 7 categories | O/B | — | list | — |

## 3. Daily reports and reconciliation

| Method Path | Purpose | Role | Request | Response | Validation |
|---|---|---|---|---|---|
| POST /daily-reports | submit report | O/B | date, branch (B: ignored), total_sales, orders, cash, pos, bank_transfer, link_payment, shop_expenses, shop_savings | report + total_received, difference, check | sales > 0; date not future (Dubai); savings ≤ expenses; amounts ≥ 0; unique branch/date → 409 |
| GET /daily-reports | history | O/B | branch (O), from, to, page | reports + check | B limited to own branch |
| GET /daily-reports/{id} | detail | O/B | — | report | branch scope |
| POST /daily-reports/{id}/void | owner correction (pending D4) | O | reason | report | reason required; audited |
| GET /daily-reports/missing | missing reports for day/month | O | date or month | branches/count | formula in BUSINESS_LOGIC §11 |

## 4. Dashboards and views

| GET /dashboard/owner | KPIs, cash board, sales by branch, day-by-day, branch-by-branch | O | mode (day/month), date or month | KPI payload | — |
| GET /dashboard/branch | own KPIs, recent reports | B | — | KPI payload | — |
| GET /branch-date-view | summary + report rows + head office rows (O only) | O/B | branch, from, to | view payload | range ≤ limit; B own branch |
| GET /alerts | Needs attention list (registry) | O | — | alerts with type, count, link | — |

## 5. Finance

| GET /opening-balances | settings, branch cash, supplier owed | O | — | settings | — |
| PUT /opening-balances | save atomically | O | as_of_date, receipts_bank, enbd, adcb, pos_pending, savings_bf, branch_cash[10], supplier_owed[] | settings + start_date | amounts ≥ 0; confirm if data exists |
| GET /cash-banks | cards, opening table, movements (latest 25) | O | — | payload | — |
| GET /cash-banks/board | cash and bank tables for a period | O | from, to | board | before start date → note |
| POST /head-office-expenses | add | O | date, branch (null=All), category_id, amount, paid_from, note, is_saving | expense | amount > 0 |
| GET /head-office-expenses | list | O | filters, page | list | — |
| PATCH /head-office-expenses/{id}/saving | mark/unmark | O | is_saving | expense | audited |
| POST /head-office-expenses/{id}/void | correction (D4) | O | reason | expense | audited |
| GET /expenses/summary | cards and per-branch shop expenses | O | range | summary | — |

## 6. Suppliers

| GET /suppliers | list + totals | O | page | list | — |
| POST /suppliers, PATCH /suppliers/{id} | add/edit (D14) | O | name, category, terms, amount_owed, active | supplier | — |
| POST /suppliers/{id}/mark-paid | sets owed to 0 (or ledger payment per D5) | O | amount? | supplier | audited |

## 7. Employees, leave, visas, passports

| GET /employees | list + cards | O | filters | list | — |
| POST /employees, PATCH /employees/{id} | add/edit (D14) | O | name, branch, role, salary, visa_expiry, passport_expiry, status | employee | leave_start iff Leave |
| POST /employees/{id}/leave | mark on leave | O | date | employee | date not future |
| POST /employees/{id}/return | mark returned | O | date | employee | applies permanent-cancel rule |
| PATCH /employees/{id}/expiry | update visa or passport expiry | O | document, date | employee | valid date |
| GET /compliance/visas-passports | statuses and cards | O | filters | list | colours/status computed |

## 8. Trade licences

| GET /trade-licenses | list + cards | O | filters | list | — |
| POST /trade-licenses | add | O | branch, license_no, authority, expiry, renewal_fee | licence | fee ≥ 0 |
| POST /trade-licenses/{id}/renew | add one year | O | — | licence | audited |

## 9. Rentals and cheques

| GET /rental-agreements | list + cards | O | filters | list | — |
| POST /rental-agreements/preview | schedule from rules | O | rent, n, first date, first no., bank | cheque rows | n 1–12 |
| POST /rental-agreements | create agreement + cheques atomically | O | branch, landlord, unit, start, end, rent, cheques[] | agreement | end > start; cheque sum = rent |
| POST /rental-agreements/{id}/renew | renew atomically | O | — | agreement | rules in BUSINESS_LOGIC §9 |
| GET /rental-agreements/{id}/cheques | schedule | O | — | cheques | — |
| POST /rental-agreements/{id}/cheques | add cheque | O | no, bank, date, amount | cheque | — |
| PATCH /pdc-cheques/{id} | change date (pending/bounced) | O | date | cheque | status check |
| POST /pdc-cheques/{id}/clear, /bounce | status change | O | — | cheque | audited; affects bank balance |
| GET /pdc-cheques/due | next 30 days | O | — | list | — |

## 10. Tasks

| GET /tasks | board | O | filters | tasks | — |
| POST /tasks, PATCH /tasks/{id} | create/update/assign | O | title, branch, assignee, due | task | — |
| POST /tasks/{id}/start, /done | status | O | — | task | — |

## 11. Reports and analytics

| GET /reports/daily, /reports/monthly | summaries | O | range | report | — |
| GET /reports/branch-comparison | branch compare | O | range | table + chart data | — |
| GET /reports/financial-summary | financial summary | O | range | payload | — |
| GET /exports/{report}.xlsx, .pdf | exports | O | same filters | file | catalogue per D15 |

## 12. Settings and audit

| GET /audit-log | entries | O | user, table, date, page | list | — |
| GET /settings | thresholds, categories | O | — | settings | — |

## 13. Cross-cutting

Pagination and filters on lists; idempotency key header on money-posting creates; 401 (no/invalid token), 403 (role/branch), 404 (outside scope — branch users get 404, not 403, for other branches), 409 (duplicate), 422 (validation). Rate limiting on auth and exports. OpenAPI docs enabled in non-production only.

## 14. Optional (Step 13, not approved)

/customers, /orders (search by id/phone/name), /orders/{id}/payments, /deliveries/today, /pickups/today, /orders/pipeline, /order-reports, /order-exports. Not part of core.
