# SEED_DATA — Step 2

Only approved static configuration is seeded (0009, idempotent via `ON CONFLICT (name) DO NOTHING`).

**branches** (sort_order 1-10, all active): ALSAFA MAIN, JERNAS, SATWA, BURDUBAI, NDL, AL BARSHA, MIRDIF, AL JADDAF, KARAMA, SALES TEAM.

**expense_categories** (7): Detergent & chemicals, Utilities, Rent, Repairs, Transport, Packaging, Salaries.

Banks (ENBD, ADCB), payment sources (Cash received, ENBD, ADCB), statuses and role names are CHECK constraints, not tables. Currency is AED by convention (no column).

**Not seeded (by design):** opening balances (decision D1 pending), users/profiles, suppliers, employees, salaries, licences, rentals, cheques, tasks, reports, expenses, any transaction. The audit trigger records the 17 seed inserts with no actor; this is expected.

Test fixtures (invented, clearly labelled) exist only inside the test suite and are rolled back.
