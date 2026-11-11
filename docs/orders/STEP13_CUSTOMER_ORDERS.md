# Step 13 — Customer Order Management, Pickup & Delivery Operations

Status: implemented and tested locally. **Supabase Auth was simulated in the browser tests and nothing has been deployed.** Items that need a client decision are numbered **O1–O14** in section 11 and are not silently decided: each lists what was built so the system works, and what to confirm.

Scope exclusions (as requested): public customer portal, mobile driver app, GPS tracking, route optimisation, online payment gateway, automated WhatsApp messages.

## 1. What was added

| Area | Where |
|---|---|
| Database | `database/migrations/0017_customer_orders.sql` — `service_categories`, `customers`, `orders`, `order_payments`, `order_status_history`, order-number sequence, triggers, RLS, audit triggers |
| Rules | `backend/app/core/orders.py` (workflow, payment arithmetic, mobile numbers, Dubai schedule times) |
| API | `backend/app/api/v1/customers.py`, `orders.py`, `order_operations.py` (services in `services/order_service.py`, `order_insights_service.py`; SQL in `repositories/order_repository.py`) |
| Front end | `frontend/src/pages/orders/*`, `schemas/orders.ts`, `services/orders.service.ts`, `hooks/use-orders.ts` |
| Navigation | New group **Orders & Delivery**: Order Management, Orders, Customers, Pickup & Delivery, Order Reports |

Step 12's report framework is extended, not duplicated: order reports return the same `ReportOut` table shape, use the same limits (`MAX_RANGE_DAYS`, `MAX_EXPORT_ROWS`) and the same CSV/Excel writers (`export_service`).

## 2. Customers

* Fields: name, mobile, WhatsApp (optional, only when different), address, area, notes. Each customer belongs to **one branch**.
* A customer can be created on the Customers page or inside the New Order form. The New Order form can search existing customers by name or mobile and select one.
* **Duplicates:** the mobile number is stored in international form (`+9715XXXXXXXX`) and is unique per branch. `0501234567`, `501234567`, `971501234567` and `+971501234567` are the same number. A second customer with the same number is refused with a message naming the existing customer (HTTP 409 `duplicate_customer`).
* **Validation:** UAE numbers must be valid UAE mobiles; other countries need a `+` or `00` prefix. Letters are refused.
* **Search:** by name (partial) or by mobile (digits, with or without the leading 0).
* **Order history, total billed and outstanding** are shown on the customer page. Cancelled orders are excluded from billed and outstanding.
* **Branch isolation:** a Branch User sees and edits only their own branch's customers; another branch's customer behaves as if it does not exist (also enforced by RLS). Customers are never deleted.
* No customer portal: customers have no login.

## 3. Orders

* **Order ID:** `ORD-000001`, `ORD-000002`, … from a database sequence. It is unique, never reused and does not reset by branch.
* **Fields:** customer, branch, order date, service category, Standard/Express, notes, pickup date/time/address (optional), expected delivery date/time/address, Order Total, Discount, Service Fee, and the payment fields described in section 6. All times are **Asia/Dubai**.
* **Service categories** are rows in `service_categories` (seeded: Wash & Fold, Wash & Iron, Ironing, Dry Cleaning, Shoes, Curtains, Carpets, Bulky, Other). They are configurable data; there is no admin screen yet (O9).
* **Validation (API, then repeated in the form):** delivery cannot be earlier than pickup; pickup date and time are given together or not at all; no negative amounts; at most two decimals; the discount cannot exceed total + service fee; the final payable amount must be above zero; the order date cannot be in the future; the category must be active. The database repeats the amount and schedule checks as constraints.
* **Duplicate submits:** the form sends a one-time key. A double click or retry returns the first order instead of creating a second one.
* **Editing:** an order that is not Delivered or Cancelled can be edited. The customer and branch cannot be changed (O7). A change that would make the final payable amount lower than what was already collected is refused. Edits take an optional reason and are written to the audit log.

## 4. Status lifecycle

```
New → Scheduled → Picked Up → Processing → Ready → Out for Delivery → Delivered
 └────────────── Cancelled (from New, Scheduled, Picked Up, Processing or Ready) ──┘
```

* One step forward at a time; skipping and going backwards are refused by the API **and** by a database trigger.
* Every change is written to `order_status_history` (from, to, who, when, note) by a trigger, so it cannot be skipped by any code path. The order page shows it as the status timeline.
* **Cancellation** needs a reason (3+ characters) and an explicit confirmation. The order and every payment are kept. A cancelled order cannot be changed, paid or reopened. **Only the Owner can cancel** (O2). An order that is Out for Delivery or Delivered cannot be cancelled (O3).
* **Delivered and Cancelled orders are final.** There is no delete endpoint and the database refuses deletes.

## 5. Pickup & Delivery operations

Screen **Pickup & Delivery** (`/order-operations`), for one chosen Dubai date, filterable by branch (Owner), searchable by order ID, customer name or mobile, sortable by delivery time, pickup time, order number or customer. Each view shows its live count.

| View | Definition |
|---|---|
| Today's Pickups | Pickup time falls on the chosen date; not cancelled |
| Today's Deliveries | Expected delivery falls on the chosen date; not cancelled |
| Pending Pickups | Status New or Scheduled, with a pickup time |
| Overdue Pickups | Pending pickup whose time has passed |
| Processing / Ready / Out for Delivery | By status |
| Overdue Deliveries | Not Delivered/Cancelled and the expected delivery time has passed |
| Unassigned / Incomplete | Open orders with no delivery address, or New/Scheduled orders with no pickup time (O5) |

Each row can open the order or move it to its next status in one click (the server still validates). **No GPS, route optimisation or live tracking.** There is no driver/assignee field (O5).

## 6. Order payments

* Several payments per order; each is independent and records date, amount, method (**Cash, POS, Bank Transfer, Payment Link**), reference, note and the user.
* Payments are append-only: no edit and no delete (database privileges and trigger). A mistake is handled by a refund once a refund workflow is approved (O4).
* Formulas (the server is the only place they are computed; the form shows a preview):

```
Final Payable  = Order Total − Discount + Service Fee
Amount Collected = sum of payments on the order
Outstanding    = Final Payable − Amount Collected
Payment status = Unpaid (collected = 0) | Partial (0 < collected < final) | Paid (collected ≥ final) | Refunded (reserved)
```

* **No overpayment:** a payment above the outstanding balance is refused. A payment on a cancelled order is refused.
* A payment can be taken while the order is placed (**Payment taken now**), and more are added later from the order page.
* **Refunds:** `POST /orders/{id}/refund` exists only as a guarded endpoint (Owner) and always answers HTTP 409 "refunds need an approved workflow". Status `Refunded` is reserved. No money is ever removed silently (O4).
* Each payment form carries a one-time key, so a double click records one payment.

## 7. Financial integration (decision recorded, not assumed — O6)

Customer-order money is kept **separate** from the existing finance modules:

* **Revenue** = final payable of non-cancelled orders, by order date. **Collections** = payments recorded on those orders. **Outstanding** = revenue − collections. These are three different figures and are never mixed.
* Order revenue and payments are **not** added to Daily Reports sales, the Owner dashboard sales/received figures, or Reports & Analytics sales. Verified by tests (section 10).
* Order payments are **not** posted to Cash & Banks, so nothing is counted twice. No ledger rows are created. Posting would need the client to confirm which account each method lands in (Cash → which branch cash? POS and Payment Link → settlement timing, as Step 8's POS rules show), and whether daily-report sales already include order sales. Until then, order collections are reported only in Order Reports.
* No schema change to the finance tables was made. If the client wants the link, the safe route is a one-way, once-only posting from `order_payments` into the Cash & Banks ledger keyed by payment id, with the Daily Reports total left alone.

## 8. Roles and permissions (no new roles — O1)

Only **Owner** and **Branch User** exist; no Admin, Operations, Delivery or Finance roles were created.

| Module | Owner | Branch User |
|---|---|---|
| Orders | read, create, update, export, **cancel** (all branches) | read, create, update, export (own branch) |
| Customers | read, create, update (all branches) | read, create, update (own branch) |
| Order payments | read, create, refund-attempt (all branches) | read, create (own branch) |

Enforced in three places: the front-end menu and routes (display only), the FastAPI permission dependency (403 plus an ACCESS_DENIED audit record), and PostgreSQL row-level security (`app.can_access_branch`), so a direct SQL session as a Branch User still cannot read or write another branch's customers, orders, payments or history. A Branch User passing another branch's id gets 403/404.

The Branch User permissions are a **working assumption** — the earlier roles document gave Branch Users only Daily Reports. Please confirm (O1).

## 9. API (all under `/api/v1`, bearer token required)

| Method and path | Purpose |
|---|---|
| `POST /customers` · `GET /customers?q=&branch_id=&page=` · `GET/PUT /customers/{id}` · `GET /customers/{id}/orders` | Customers |
| `POST /orders` · `GET /orders` (filters below) · `GET/PUT /orders/{id}` | Orders |
| `POST /orders/{id}/status` · `POST /orders/{id}/cancel` · `GET /orders/{id}/status-history` | Workflow |
| `GET/POST /orders/{id}/payments` · `GET /orders/{id}/balance` · `POST /orders/{id}/refund` (409) · `GET /orders/payments/summary` | Payments |
| `GET /orders/service-categories` · `GET /orders/dashboard?date=&branch_id=` | Lookups, dashboard |
| `GET /order-operations/counts` · `GET /order-operations/{view}` | Operations |
| `GET /orders/reports/catalog` · `GET /orders/reports/{key}` · `GET /orders/reports/{key}/export?format=csv\|xlsx` | Reports |

`GET /orders` filters: `q` (order ID, name or mobile), `status`, `payment_status`, `category_id`, `service_type`, `area`, `date_from`/`date_to` (order date), `pickup_date`, `delivery_date`, `branch_id`, `sort`, `desc`, `page`, `page_size`.

Order reports: Order totals (count, completed, cancelled, revenue, collections, outstanding, average order value), Orders by service category, Standard vs Express, Order trend (daily or weekly), Orders by branch, Order payments by method, Outstanding order payments, Order list. Exports are built by the server from the same filters and the same branch scope as the screen; a Branch User's file contains only their branch. The live OpenAPI page is authoritative for field names.

## 10. Database migration

`0017_customer_orders.sql` — apply once, after 0016, as the database owner. It creates 5 tables, 1 sequence, triggers (`customers_before`, `orders_before` incl. the workflow, `orders_history`, `order_payments_before`, `order_payments_after`), audit triggers, RLS policies and grants (no delete on any of the new tables; payments are insert-only). It changes **no** existing table. Seed: the nine service categories. Rollback: drop the five tables, the sequence and the `app.*` trigger functions (no other object depends on them).

## 11. Testing results (this environment)

| Check | Result |
|---|---|
| Backend `pytest` (includes 32 new Step 13 tests) | 560 passed, 1 skipped (the skip is the pre-existing optional `TEST_DATABASE_URL` test) |
| Database tests | 162 passed |
| `ruff check`, `ruff format`, `mypy app` | clean |
| Front end `vitest` (30 new tests) | 285 passed |
| `tsc -b`, `eslint`, `prettier --check`, `vite build` | clean; build succeeds (the chunk-size notice is the existing one) |
| End-to-end (real React app + real FastAPI + real PostgreSQL + RLS, **simulated** Auth server) | **122/122 scenarios passed** (103 earlier + 19 new Step 13: access control, workflow, payments, cancellation, branch isolation, finance separation, reports/exports, UI flows, layouts at 390/768/1440 px) |

The browser tests used a **simulated Auth server**, not real Supabase. Nothing was deployed and nothing was tested against a real Supabase project.

Bugs found by the end-to-end run and fixed in this step: the payment endpoint returns a balance (the form expected a full order); order creation had no replay protection of its own (a retried submit with a new customer was refused as a duplicate instead of returning the first order).

## 12. Limitations and unresolved decisions (need client approval)

| # | Decision | What was built meanwhile |
|---|---|---|
| O1 | Branch User access to orders, customers and payments | Own-branch read/create/update/export; no cancel, no refund |
| O2 | Who may cancel an order | Owner only; reason and confirmation required |
| O3 | Cancelling after pickup, or once out for delivery | Allowed up to Ready; refused when Out for Delivery or Delivered |
| O4 | Refund workflow (who approves, how money returns, which account) | Not built. Endpoint answers 409; `Refunded` reserved. Payments never deleted |
| O5 | "Unassigned" orders and staff assignment (driver/collector) | No assignment field. "Unassigned or Incomplete" means missing delivery address or, for New/Scheduled, missing pickup time |
| O6 | Link to Cash & Banks / Daily Reports | None: kept separate (section 7) |
| O7 | Changing the customer or branch of an existing order | Not allowed; cancel and re-create |
| O8 | Walk-in customers with no mobile | Mobile is required |
| O9 | Admin screen for service categories | Categories are data; no screen yet |
| O10 | Revenue basis | By order date, excluding cancelled; not by delivery date |
| O11 | Overdue definitions (section 5) and "today" = Dubai calendar day | As written |
| O12 | WhatsApp field | Stored only; nothing is sent |
| O13 | Order-number format and reset | `ORD-000001`, global, never reset |
| O14 | Express surcharge / price lists | Not calculated: the staff enter the total, discount and fee |

Other limits: report ranges are limited to 366 days and exports to 100,000 rows (same as Step 12); there is no printed invoice/receipt; no automatic status changes; export downloads are not recorded in the audit table (same as Step 12, X1).
