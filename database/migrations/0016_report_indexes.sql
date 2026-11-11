-- Step 12: indexes for the Reports & Analytics queries and the Activity History. Additive; no data or rule changes.
create index if not exists pdc_cleared_on_idx  on public.pdc_cheques (cleared_on) where cleared_on is not null;
create index if not exists pdc_bounced_on_idx  on public.pdc_cheques (bounced_on) where bounced_on is not null;
create index if not exists tasks_completed_idx on public.tasks (completed_at) where completed_at is not null;
create index if not exists audit_table_time_idx on public.audit_log (table_name, occurred_at desc);
create index if not exists lr_renewed_on_idx   on public.license_renewals (renewed_on);
create index if not exists ra_start_idx        on public.rental_agreements (start_date);
