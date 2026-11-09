# BUSINESS_LOGIC — ALSAFA Heritage Laundry ERP

Source: Technical Summary section 4 (and sections 3, 7), unless marked otherwise. These rules are preserved as written. Anything marked **[AMBIGUOUS]** is not resolved here; see OPEN_DECISIONS.md. Prototype and SQL (`app_balances()`) unseen: **[VERIFY]**.

Conventions (proposal, not from PDFs): currency AED stored as numeric(14,2); dates are calendar dates; "today" and "no future dates" use Asia/Dubai time (PDF: "future-dated reports refused (Dubai time)").

## 1. Data ownership: global vs per branch

| Data | Scope |
|---|---|
| Daily reports (sales, collections, shop expenses, shop savings) | Per branch, per day |
| Opening cash | Per branch (`opening_branch_cash`) |
| ENBD / ADCB balances, POS settlements pending, savings brought forward, receiving bank | Global (single settings row) |
| Head office expenses | Global; optional branch tag ("All" = no branch) |
| Suppliers and amounts owed | Global (opening owed per supplier) |
| Employees | Per branch (employee has a branch) |
| Trade licences | Per branch (many per branch) |
| Rental agreements and cheques | Per branch |
| Tasks | Per branch or "All" |
| Cash and bank balances (cash board) | Computed globally; per-branch cash is **[AMBIGUOUS]** (D18) |

## 2. Sales and reconciliation (module: Daily Reporting / Reconciliation)

| Calculation | Inputs | Formula | Output |
|---|---|---|---|
| Total received (collections) | cash, POS, bank transfer, link payment | cash + POS + bank transfers + link payment | AED amount |
| Reconciliation difference | total sales, total received | total sales − total received | 0 shows "Matches", otherwise the difference |
| Not yet received | total sales, total received | total sales − total received (same as difference) | AED amount |
| Check column | difference | "Matches" or "Diff" | label |

Report rules: date and sales > 0 required; savings cannot exceed shop expenses; no future dates (Dubai time); one report per branch per day (duplicates refused); no edit (prototype). After saving, show whether receivings match sales or differ.

## 3. Expenses and savings (module: Expenses & Savings)

| Calculation | Formula |
|---|---|
| Shop expenses (excl. savings) | shop expenses − shop savings |
| Head office expenses (excl. savings) | head office total − items marked saving |
| Savings (period) | shop savings + head office items marked saving |
| Sales minus expenses | sales − shop expenses (excl. savings) − head office expenses (excl. savings) |
| Savings total | savings brought forward + shop savings + head office savings, entries on/after start date |

Head office expense: categories fixed list of 7 (Detergent & chemicals, Utilities, Rent, Repairs, Transport, Packaging, Salaries); paid from Cash received, ENBD or ADCB; branch optional ("All"); can be marked/unmarked as saving.
**[AMBIGUOUS]** Savings are never withdrawn (D21).

## 4. Opening balances and the start date (module: Opening Balances)

- Tracking start date = opening ("balances as at") date + 1 day. Default as-at date in prototype: 30 Sep 2026 → start 1 Oct 2026 (**D1**: client wrote 30 August).
- Only entries dated on or after the start date count in balances.
- Settings: receiving bank (ENBD or ADCB) for POS/transfers/links; opening cash for each of 10 branches; ENBD balance; ADCB balance; POS settlements pending; savings brought forward; opening owed per supplier.

## 5. Cash and banks (module: Cash & Bank Management)

| Calculation | Formula |
|---|---|
| Cash now | opening cash (sum of branches) + cash received − shop expenses (**including** savings) − head office paid from "Cash received" |
| Bank now, per bank | opening balance + (POS + transfers + links, only for the receiving bank) − head office paid from that bank − rent cheques cleared on that bank |
| Total cash + banks | cash now + ENBD now + ADCB now |
| Cheque timing | cheques count on their cheque date |
| Cash board closing (any period) | opening (balance the day before the period) + the period's flows |
| Before start date | show a note instead of the board |

Dashboard cash table columns: opening, cash received, shop expenses, head office paid from cash, closing. Bank table columns: opening, POS, transfers, links, head office paid from banks, rent cheques cleared, closing.
Cash & Banks cards: Total cash + banks, Cash in hand, ENBD, ADCB, POS settlements pending, Savings (incl. brought forward).

**[AMBIGUOUS]** D18 (per-branch cash), D19 (POS pending), D20 (cash↔bank transfers), cleared cheques of status handling when later set back to pending/bounced.

## 6. Suppliers (module: Supplier Management)

- Outstanding dues = sum of amount_owed over suppliers (Total owed card); Active suppliers count.
- Prototype: "Mark paid" sets owed to 0. Opening owed set in Opening Balances.
- **[AMBIGUOUS]** No bills/payments recorded; see D5.

## 7. Employees, leave, visas and passports (modules: Employee Management; Salary & Leave; Visa & Passport)

| Rule | Detail |
|---|---|
| Status | Active or Leave. Leave start required exactly when status is Leave. Date not in the future. |
| Visa limit on leave | leave_start + 6 calendar months. After that date the visa shows as cancelled. |
| Permanent cancellation | Returning after the limit sets visa_cancelled permanently. |
| Days on leave | computed from leave start |
| Close to 6 months | staff within 30 days of the 6-month limit (alert) |
| Monthly payroll | sum of salary for **active** staff only (assumption: leave is unpaid; D6) |
| Visa colour | red at ≤ 30 days (or expired); amber at ≤ 90 days |
| Passport colour | red at ≤ 30 days; amber at ≤ 180 days |
| Cards | Visas expiring in 30 days; Passports expiring in 30 days; Passports under 6 months left; Visas cancelled |
| Sort | cancelled visas first, then earliest expiry |

Passport and Emirates ID numbers are not stored. Salary, visa and passport data are owner-only.

## 8. Trade licences (module: Trade License Management)

- Expiring within 60 days (card). Renewal fees due = sum of renewal_fee for licences expiring within 90 days.
- Alert: licence within 30 days.
- "Mark renewed" adds one year to expiry. Renewal history is not kept in the prototype (D9).

## 9. Rental agreements and PDC cheques (modules: Rental Agreements; PDC Cheque Management)

| Rule | Detail |
|---|---|
| Cheque count | 1 to 12 |
| Cheque amount | annual rent ÷ number of cheques, rounded; last cheque takes the remainder (so total = annual rent) |
| Cheque k date | first cheque date + round(12 × k ÷ n) months |
| Default end date | start + 12 months − 1 day |
| Total check | editable cheque rows show total versus annual rent |
| Cheque status | Pending, Cleared, Bounced. Pending/bounced dates editable. |
| Cheques due (30 days) | Pending cheques dated within 30 days or already past |
| Next cheque | earliest cheque not cleared |
| PDC alert | pending cheques due within 7 days; bounced cheques alert |
| Agreement ending alert | ending within 30 days |
| Renew | new start = old end + 1 day; new end = one year later; same rent and cheque count; cheque numbers continue; all cheques reset to Pending. Done atomically. |
| Cleared cheque effect | reduces the bank it is drawn on, on the cheque date |

Cheque no., bank (ENBD/ADCB), date, amount per cheque. Agreement creation inserts agreement and all cheques in one transaction.
**[AMBIGUOUS]** Rounding method (which half-rule), month arithmetic for 29–31 dates, and what happens to bank balance if a cleared cheque is later changed.

## 10. Tasks (module: Task Management)

- Statuses: To do (0), In progress (1), Done (2). Overdue = due date passed and not Done.
- Branch: All or one. New tasks "Unassigned" in prototype (assignee is text). Owner assignment to users is new scope (D22).

## 11. Missing reports (module: Dashboard / Alerts)

- Day mode: branches with no report for the day.
- Month mode: (days so far × 10 branches) − reports received.
- Branch & date view, one branch selected: days without a report show "Report not submitted", up to 92 days.
- **[AMBIGUOUS]** closed days/holidays and SALES TEAM (D13).

## 12. "Needs attention" alerts (module: Alerts & Notifications)

1. Missing reports
2. Visas within 30 days
3. Visas cancelled by leave
4. Staff within 30 days of the 6-month limit
5. Passports within 30 days
6. Overdue tasks
7. Licences within 30 days
8. Rental agreements ending within 30 days
9. Bounced cheques
10. PDCs due within 7 days
11. Amount owed to suppliers

On-screen only in the prototype (D25).

## 13. Dashboard KPIs (Day or Whole month)

Sales; Total received; Shop expenses (excl. savings); Head office expenses (excl. savings); Savings; Sales minus expenses; Orders (sum of order_count from daily reports); Cash + bank balance now. Plus cash board, Needs attention, Sales by branch bars, Day by day table (month mode), Branch by branch table.

Branch & date view also shows: Not yet received; receivings split (cash, POS, bank transfers, link payment, orders); reports table with totals; head office expenses table with totals. Filters: branch, from/to, Today / Yesterday / Last 7 / Last 14 days.

## 14. Edge cases to carry into tests

- Sales = 0 report (rejected); savings > shop expenses (rejected); duplicate branch/day (rejected); future date (rejected).
- Reports and expenses before the start date do not affect balances.
- Month with 29–31 day cheque dates; remainder cheque; 1-cheque and 12-cheque agreements.
- Leave start on month-end dates (6 calendar months); returning exactly on and after the limit.
- Cheque cleared then marked bounced.
- Savings toggle on a head office expense paid from bank vs cash.
- Branch "All" head office expenses in per-branch views.

## 15. Optional module (Step 13) logic — not approved

From the second PDF (all sample numbers illustrative): order status flow New → Scheduled → Picked Up → Processing → Ready → Out for Delivery → Delivered / Cancelled; payment status Unpaid / Partial / Paid / Refunded; multiple payments per order; outstanding = order total − collected; AOV = gross sales ÷ orders. Not part of the core implementation.
