# UI_UX_STRUCTURE — ALSAFA Heritage Laundry ERP

Direction: modern enterprise ERP, light theme by default with a user-selectable dark theme (D24), navy and professional-blue accents, white/light-grey surfaces, consistent typography, clean sidebar, KPI cards, Recharts charts, responsive tables and forms. The second PDF is a visual reference only (KPI row, pipeline panel, quick actions, report slicers); its order-centric content is not part of core navigation.

## 1. Route hierarchy

```
/login  /forgot-password
Owner (guarded: role=owner)
 /                      Dashboard
 /branch-date-view      Branch & date view
 /daily-reports         Daily reports (list, new, detail)
 /cash-banks            Cash & banks
 /opening-balances      Opening balances
 /expenses              Expenses & savings
 /suppliers             Suppliers
 /employees             Employees (+ leave status)
 /compliance            Visas & passports
 /trade-licenses        Trade licences
 /rentals               Rental agreements → /rentals/:id (PDC schedule)
 /tasks                 Tasks
 /reports               Reports & analytics
 /settings/users | branches | categories | audit-log
Branch User (guarded: role=branch)
 /b                     Branch dashboard
 /b/report/new          Submit daily report
 /b/reports             My report history
 /b/profile             Profile
Optional (Step 13, not approved): /orders, /customers, /deliveries, /order-reports
```

## 2. Owner navigation (sidebar groups)

Overview: Dashboard, Branch & date view · Operations: Daily reports, Tasks · Finance: Cash & banks, Opening balances, Expenses & savings, Suppliers · People & compliance: Employees, Visas & passports, Trade licences · Property: Rentals & PDC cheques · Insights: Reports & analytics · Admin: Users, Branches, Categories, Audit log.
Header: branch/global context, date control where relevant, alerts bell (Needs attention count), user menu.

## 3. Branch User navigation

Four items: Dashboard, Submit report, My reports, Profile. Mobile-first layout; bottom tab bar on phones. No owner links rendered (and backend rejects them regardless).

## 4. Mobile behaviour

Sidebar becomes a drawer with grouped items (prototype uses a scrolling top menu). Tables collapse to stacked cards below tablet width with primary columns first. Report form single column with large numeric inputs and live totals.

## 5. Shared components

AppShell, Sidebar, Header, KpiCard, StatusBadge (colour rules), DataTable (TanStack Table: search, filters, sort, pagination, totals row), FilterBar (branch, date range, quick ranges), DateModePicker (Day/Month with prev/next/today), MoneyText (AED), FormField wrappers (React Hook Form + Zod), ConfirmDialog, Modal/Drawer, ChartCard (Recharts), AlertList, EmptyState, ErrorState, Skeletons, ExportMenu, AuditReason dialog (owner corrections).

## 6. Page-specific components

- Dashboard: KPI grid, CashBoardTables, NeedsAttention, SalesByBranchBars, DayByDayTable, BranchByBranchTable.
- Daily report: ReportForm (10 fields, live total received and difference), ConfirmationPanel (Matches/Diff), ReportsTable with Check column.
- Rentals: AgreementForm with ChequeScheduleEditor (one row per cheque, total versus rent), AgreementsTable, ChequeSchedulePanel, DueChequesList.
- Employees/compliance: StatusUpdateForm, LeaveBadge, ExpiryBadge.
- Tasks: three-column board.
- Settings: UsersTable, UserForm, AuditLogTable.

## 7. Forms and tables

Forms: React Hook Form + Zod; schema mirrors backend; inline errors; disabled submit while pending; confirmation for destructive/owner-correction actions; AED inputs numeric with 2-decimal limit; date inputs reject future dates where required.
Tables: server-side pagination, search, filters, sorting; totals row where the prototype has one; row actions gated by role; export via ExportMenu (owner).
State: server state in TanStack Query (per-feature keys, invalidation after mutations); form state local; auth/session in a small context; URL carries filters (shareable). API layer: one Axios instance with token interceptor and error normalization; per-feature `api` modules; no direct Supabase table calls.
States: every page defines loading skeleton, empty state with next action, and error state with retry; 401 redirects to login; 403/404 show safe pages.

## 8. Dashboard specifics

Owner dashboard: mode toggle, 8 KPI cards, cash board, Needs attention, sales by branch, day-by-day (month mode), branch-by-branch. Branch dashboard: own KPI cards, recent submissions, today's submission status.

## 9. Accessibility and quality

Sufficient contrast with navy/blue palette; keyboard-operable forms and dialogs; status never conveyed by colour alone (labels like Matches/Diff); AED and dates formatted consistently.

## 10. Optional order screens (Step 13, not approved)

Orders list/new-edit form, today's pickups/deliveries, order pipeline, payment follow-up, report slicers. Defined in PROJECT_REQUIREMENTS §23.
