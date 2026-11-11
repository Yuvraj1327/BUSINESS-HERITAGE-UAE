# UI_TEST_RESULTS

Executed in this build. **Auth in the browser runs is a simulated Supabase (GoTrue) server**; the real Supabase project was never available, so sign-in against real Supabase remains unverified (see Step 4 docs). API and database are real (FastAPI + PostgreSQL 16 with migrations 0001–0010, restricted `app_api` role, RLS). Browser: system Chrome (headless) driven by Playwright. Test users and branch names are throw-away; branch names in the selector are the ten real seeded ones.

## Commands and results
| Check | Command | Result |
|---|---|---|
| Typecheck | `npm run typecheck` | clean |
| Lint | `npm run lint` | clean, 0 warnings |
| Format | `npm run format:check` | clean |
| Unit/component tests | `npm test` | **105 passed** (57 earlier + 48 new: `layout.test.tsx`, `components.test.tsx`, updated `rbac.test.tsx`/`auth.test.tsx`) |
| Production build | `npm run build` (public env vars only), clean `npm ci` copy | OK; main chunk 470 kB (148 kB gzip); bundle scan found no keys/JWTs |
| End to end (real browser) | `python e2e/run_e2e.py` | **45/45 scenarios passed** (25 earlier + 20 new `LAYOUT` scenarios) |
| Backend regression | `pytest`, `ruff`, `mypy` | 235 passed, 1 skipped; clean |
| Database regression | `cd database/tests && pytest` | 152 passed |

## Browser scenarios (viewport × role)
For each of **1440×900, 1280×800, 768×1024, 390×844, 360×740**, as **Owner** and as **Branch User**: every page opens (dashboard, module placeholders, Access denied, 404, system status, design system), the shell renders, `document.scrollWidth ≤ window.innerWidth` (**no horizontal overflow**), and the browser reported **no console errors or warnings** (10 scenarios).

Interaction scenarios:
| Area | What was checked |
|---|---|
| 1440 sidebar | 256px → collapse to 64px → header/content shift with it → survives reload → expand |
| 1280 | sidebar expanded by default; content fills `1280 − 256` |
| 768 | 64px icon rail; rail rows ≥ 36px; tooltip on hover; toggle opens the full drawer; choosing a link navigates and closes it |
| 390 / 360 | no fixed sidebar; header buttons ≥ 44×44px; drawer 288px at the left edge; Escape closes it and **focus returns to the toggle**; link navigation closes it; no overflow after |
| Navigation | all 7 section titles and 15 modules visible to Owner; Settings group expands; breadcrumbs `Dashboard › Administration › Settings › System status`; breadcrumb link returns home; active item has `aria-current` |
| Owner controls | branch selector lists **All branches + 10**; choosing one updates the dashboard; notification menu; user menu shows name/role; Sign out returns to login |
| Branch User | menu is exactly Dashboard, My Branch, Daily Reports (desktop and drawer); no branch selector; assigned branch visible; typed URLs `/suppliers /cash-banks /users /settings /system-status /branch-date-view /tasks` all show Access denied with the shell intact |
| Keyboard | skip link appears on first Tab and moves focus to main; focus ring present on nav links and header buttons |
Screenshots (`docs/ui/screenshots/`): dashboards at 1440 (Owner, Branch, collapsed), 768 (rail, drawer), 390 (page, drawer), Branch drawer, Access denied, user menu.

## Component and permission tests (Vitest, jsdom)
Navigation per role and default deny; Settings group; active marking; role layouts and branch context (Branch User never requests the branch list); placeholder dashboards contain no numbers; protected module routes (Access denied for the Branch User, including `/branch-date-view` by scope); 404 inside and outside the shell; breadcrumbs; collapse persistence; tablet rail and drawer; mobile drawer/Escape; user and notification menus; skip link; DataTable (rows, loading, empty, error+retry); StatCard, StatusBadge, SectionCard/PageContainer, LoadingState, PermissionDenied; ConfirmDialog (confirm, cancel, Escape, loading lock); FormInput/Textarea/DatePicker/Select/Actions.

## Defects found by testing, and fixed
1. **Rail links lost their styling**: inside the tooltip trigger, Radix `Slot` stringified the `NavLink` className function (found by looking at the 768px screenshot; now guarded by a unit test and a size check in the browser run).
2. **No focus ring on navigation links**: Tailwind v4 `outline-none` removes the outline style, so `focus-visible:outline-*` did nothing (found by the keyboard scenario).
3. **Focus was lost after closing the mobile drawer**: the drawer has no Radix trigger, so focus now returns to the menu button explicitly (found by the 390/360 scenarios).
4. **`/branch-date-view` reachable by URL** for a Branch User although hidden from the menu: route guards now honour the scope requirement (found by a unit test).
5. **React Router warning** (`HydrateFallback`) on first load of the lazy design-system route: fallback added (found by the console check).
6. **Flaky backend test (from Step 5)**: `test_rbac_api` picked random report dates and occasionally collided with a unique constraint (about 4 failures in 10 runs); dates are now distinct. 12 consecutive full runs pass.
7. Old assertions updated for the new shell (the temporary "Welcome" page is gone; Settings is a group).

## Not tested
Real Supabase sign-in; Safari, Firefox and real phones/tablets (only Chrome viewport emulation); screen readers (landmarks, names and focus order were checked programmatically only); automated contrast scanning in the browser (ratios were computed from the tokens, see `DESIGN_SYSTEM.md`); printing; slow networks.

## Remaining UI issues
- Placeholder pages and dashboards contain no data by design; the notification bell has no source yet.
- Sidebar navigation scrolls inside the sidebar on windows shorter than about 900px (Owner has 15 items).
- The native date input shows the browser's locale format (e.g. mm/dd/yyyy).
- The main JS chunk grew from 320 kB to 470 kB (Radix menus/dialogs); route-level code splitting can be revisited when modules arrive.
- Unresolved Step 5 permission decisions (D10, D11, D15, …) still decide what a Branch User will see once modules exist.
