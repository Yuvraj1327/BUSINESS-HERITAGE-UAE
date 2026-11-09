-- 0009_seed_reference_data.sql : static configuration only. Idempotent (safe to re-run).
-- No transactions, balances, employees, suppliers or salaries are seeded.

insert into public.branches (name, sort_order) values
  ('ALSAFA MAIN', 1), ('JERNAS', 2), ('SATWA', 3), ('BURDUBAI', 4), ('NDL', 5),
  ('AL BARSHA', 6), ('MIRDIF', 7), ('AL JADDAF', 8), ('KARAMA', 9), ('SALES TEAM', 10)
on conflict (name) do nothing;

insert into public.expense_categories (name) values
  ('Detergent & chemicals'), ('Utilities'), ('Rent'), ('Repairs'),
  ('Transport'), ('Packaging'), ('Salaries')
on conflict (name) do nothing;
