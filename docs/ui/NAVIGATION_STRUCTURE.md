# NAVIGATION_STRUCTURE

Single definition: `frontend/src/config/navigation.ts` (`NAV_SECTIONS`). The menu, the route table, the breadcrumbs and the page titles are all derived from it, so they cannot drift apart.

## Sections and items
| Section | Item | Route | Module / action | Notes |
|---|---|---|---|---|
| Overview | Dashboard | `/` | dashboard / read | live (placeholder content, see below) |
| Operations | Branch Management (label "My Branch" for own-branch scope) | `/branches` | branch_management / read | placeholder page |
| | Branch & Date View | `/branch-date-view` | daily_reports / read **and** scope `all_branches` | cross-branch view; no separate module in the matrix, so it maps to daily reports and requires all-branch scope |
| | Daily Reports | `/daily-reports` | daily_reports / read | placeholder page |
| Finance | Cash & Banks | `/cash-banks` | cash_banks / read | placeholder |
| | Opening Balances | `/opening-balances` | opening_balances / read | placeholder |
| | Expenses & Savings | `/expenses` | expenses / read | placeholder |
| | Suppliers | `/suppliers` | suppliers / read | placeholder |
| People & Compliance | Employees | `/employees` | employees / read | placeholder |
| | Visas & Passports | `/visas-passports` | visas_passports / read | placeholder |
| | Trade Licenses | `/trade-licenses` | trade_licenses / read | placeholder |
| Property | Rental Agreements | `/rentals` | rentals_cheques / read | placeholder |
| Management | Tasks | `/tasks` | tasks / read | placeholder |
| | Reports & Analytics | `/reports` | reports / read | placeholder |
| Administration | User Management | `/users` | user_management / read | live |
| Account | Settings (expandable group) → My Profile, Account & Security, Appearance, Notifications, Preferences, About | `/settings/*` | every signed-in user (self-service) | live, see `docs/settings/SETTINGS.md` |
| | Settings → System status | `/system-status` | settings / read (Owner) | live (Step 3 page) |

A "placeholder" page is a protected route that says "This module is not built yet"; it has no data and no actions. `/design-system` exists in development builds only and is not in the menu.

## Who sees what
Visibility = the user holds the action on the module in the **server-sent permissions** (default deny) and, where listed, the required scope. Nothing in the frontend names a role.
- Owner (all modules, all branches): all seven sections.
- Branch User (server grants dashboard, branch_management, daily_reports, own branch only): Overview → Dashboard; Operations → My Branch, Daily Reports. Everything else is absent from the menu **and** blocked if typed in the address bar (Access denied page in the shell).
- Empty sections and groups are not rendered.

Route guard and menu use the same `module`/`action`/`scope`, so a hidden link is always a blocked URL (`RequirePermission` gained a `scope` prop for this; a test caught `/branch-date-view` being reachable by URL before it was added). The API and database still make the real decision.

## Behaviour
- Active item: from the router (`aria-current="page"`); the Settings group opens by itself when one of its pages is active and can be closed/opened with the keyboard.
- Breadcrumbs: Dashboard → section → (group) → page, from the same config; section labels are text, not links (sections are not pages). On phones only the current page is shown.
- Document title: `<page> · ALSAFA Heritage Laundry`.
- Unknown URL: 404 page inside the shell for signed-in users (navigation stays usable), bare 404 for visitors who are not signed in. A forbidden URL shows Access denied, never 404, never the page.
- Adding a module later: replace its placeholder in `routes/index.tsx` with the real page (keep the same guard), set `status: 'live'`; add a new item to `NAV_SECTIONS` for new modules.

## Step 13: Orders & Delivery
New group between Operations and Finance. Visible to anyone holding `orders` / `customers` read; blocked by URL otherwise.

| Entry | Path | Permission |
|---|---|---|
| Order Management | `/order-management` | orders / read |
| Orders | `/orders` (also `/orders/new`, `/orders/:id`, `/orders/:id/edit`) | orders / read (create, update for the sub-pages) |
| Customers | `/customers` (also `/customers/:id`) | customers / read |
| Pickup & Delivery | `/order-operations` | orders / read |
| Order Reports | `/order-reports` | orders / read |

A Branch User now sees: Dashboard; My Branch, Branch & Date View, Daily Reports; and the five Orders & Delivery entries (assumption O1, see `docs/orders/STEP13_CUSTOMER_ORDERS.md`).
