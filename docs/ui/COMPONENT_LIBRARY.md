# COMPONENT_LIBRARY

shadcn/ui conventions (Radix primitives + Tailwind + `cn()`), files in `frontend/src/components/`. Existing Step 3/4 components were reused, not duplicated: `EmptyState`, `ErrorState`, `FormField`, `LoadingIndicator`, `Brand`, `Badge`, `Table`, `Dialog`, `Select`, sonner toasts.

## Layout (`components/layout/`, `layouts/`)
| Component | Purpose |
|---|---|
| `AppLayout` (`layouts/`) | the shell: sidebar / rail / drawer, header, main, skip link, document title |
| `OwnerLayout`, `BranchLayout` | wrap AppLayout; Owner adds the global branch selector, Branch adds the assigned-branch label; both provide `BranchProvider` |
| `RootLayout` | picks the layout from the server-sent dashboard scope (not a role name) |
| `AppSidebar`, `SidebarContent` | brand, role-filtered navigation, user + sign-out; same content in the fixed sidebar and the drawer |
| `SidebarItem`, `SidebarGroup` | link row (tooltip when icon-only); expandable group |
| `AppHeader` | toggle, breadcrumbs, branch control, date (Asia/Dubai), notifications, user menu |
| `Breadcrumbs` | trail for the current route |
| `UserMenu`, `UserAvatar` | account dropdown (name, role, branch, Sign out) |
| `NotificationMenu` | bell; states plainly that there are no notifications (no source exists yet) |
| `BranchSelector`, `AssignedBranch` | global branch filter (all-branch scope) / read-only assignment |
| `PageContainer`, `PageHeader` | standard page frame; title, description, actions |

## Data display (`components/common/`)
| Component | Notes |
|---|---|
| `StatCard` | label + value; `placeholder` shows an em dash, never a number; `isLoading` skeleton |
| `SectionCard` | titled white surface with optional header actions |
| `StatusBadge` | `success | warning | danger | info | neutral`; dot + text |
| `DataTable<T>` | typed columns; loading skeleton rows, empty and error states (retry); right-aligned numbers; scrolls inside its own container; sorting/paging are left to the modules that need them |
| `EmptyState`, `ErrorState`, `LoadingIndicator` | existing |
| `LoadingState` | content skeleton lines (`role=status`) for a section that is loading |

## Forms (`components/forms/`, with existing `common/form-field`)
`FormInput`, `FormTextarea`, `FormDatePicker` (native date input, `YYYY-MM-DD`; pass `max={dubaiToday()}` where future dates are not allowed), `FormSelect` (use with react-hook-form `Controller`), `FormActions` (Cancel + Submit, busy state, stacked 44px buttons on phones). Labels, required marks, hints and errors are wired with `aria-describedby` / `aria-invalid`. Amounts: strings validated by `aedAmountSchema` (Step 3).

## Feedback
`ConfirmDialog` (built on the new `AlertDialog` primitive: destructive variant, busy state, stays open until the caller closes it, Escape/Cancel close), `PermissionDenied` (used by `ForbiddenPage`), toasts via `sonner` (`toast.success/error`).

## Primitives added to `components/ui/`
`dropdown-menu`, `tooltip`, `alert-dialog`, `sheet` (mobile drawer on the Radix dialog), `textarea`, `skeleton`; `badge` gained `info` and `neutral`.

## Rules
1. Check this list before adding a component; extend rather than copy.
2. No hex colours in components; use tokens.
3. Never put a `NavLink` className *function* inside a Radix `asChild` trigger (Slot stringifies it); compute the state and pass a string (see `SidebarItem`).
4. Interactive controls must act or be visibly inert placeholders (disabled, with text saying so).
5. The dev-only preview of everything is `/design-system` (development builds).
