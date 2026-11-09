# TABLE_RELATIONSHIPS — Step 2

All foreign keys are `ON DELETE RESTRICT` (history is never silently removed).

| Child (column) | Parent | Notes |
|---|---|---|
| profiles.user_id | auth.users.id | Supabase-managed table, referenced only |
| profiles.branch_id | branches.id | null for owner |
| opening_branch_cash.branch_id | branches.id | PK, one row per branch |
| daily_reports.branch_id | branches.id | |
| daily_reports.created_by | auth.users.id | default auth.uid() |
| head_office_expenses.branch_id | branches.id | null = All branches |
| head_office_expenses.category_id | expense_categories.id | |
| head_office_expenses.created_by | auth.users.id | |
| employees.branch_id | branches.id | |
| tasks.branch_id | branches.id | null = All |
| tasks.assignee_user_id | profiles.user_id | null = Unassigned |
| trade_licenses.branch_id | branches.id | |
| rental_agreements.branch_id | branches.id | |
| rental_agreements.renewed_from_id | rental_agreements.id | renewal chain |
| pdc_cheques.agreement_id | rental_agreements.id | RESTRICT (PDF cascaded; changed to protect history) |

```
branches 1─n profiles (branch users)        branches 1─n daily_reports
branches 1─1 opening_branch_cash            branches 1─n head_office_expenses (optional)
branches 1─n employees / trade_licenses / rental_agreements / tasks (optional)
expense_categories 1─n head_office_expenses
rental_agreements 1─n pdc_cheques           rental_agreements 1─0..1 rental_agreements (renewal)
profiles 1─n tasks (assignee)               audit_log: no FKs (append-only record)
opening_balances: single row (id = 1), no relations
```

Derived, not stored: reconciliation difference, balances, savings total, visa/passport status, alerts.
