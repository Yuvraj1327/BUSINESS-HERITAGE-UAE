# DESIGN_SYSTEM

Step 6 visual foundation. Light theme only (the approved design has no dark mode, so none was added). Tokens live in `frontend/src/styles/globals.css` as CSS variables exposed to Tailwind v4 through `@theme inline`; components use semantic names (`bg-primary`, `text-muted-foreground`), never raw hex values.

## Colour tokens
| Token | Value | Use |
|---|---|---|
| `--primary` / `--sidebar` | `#173B63` navy | headings, primary buttons, sidebar |
| `--accent` / `--ring` | `#2563A8` blue | links, accent buttons, focus ring |
| `--teal` | `#16A085` | icons, small highlights |
| `--teal-strong` | `#0F7A64` | teal where text sits on or beside it |
| `--background` | `#F5F7FA` | page canvas |
| `--card` | `#FFFFFF` | content surfaces |
| `--border` | `#E5EAF0` | dividers, card borders |
| `--foreground` | `#172B4D` | primary text |
| `--muted-foreground` | `#5A6A80` | secondary text |
| `--input` | `#8795A8` | form control borders |
| `--destructive` / `--success` / `--warning` | `#B91C1C` / `#15803D` / `#B45309` | status text |
| `--sidebar-foreground`, `-muted`, `-accent`, `-border` | `#E2E8F0`, `#B8C7DB`, `#24507F`, `#2C5280` | sidebar text, labels, active row, rules |

### Deliberate deviations from the suggested palette (accessibility)
| Suggested | Used | Why |
|---|---|---|
| Text secondary `#64748B` | `#5A6A80` | `#64748B` on the `#F5F7FA` canvas is 4.43:1 (below AA 4.5:1); `#5A6A80` is 5.14:1 |
| Accent teal as a text background | teal only for icons/shapes; `#0F7A64` for text | white on `#16A085` is 3.28:1; `#0F7A64` on white is 5.27:1 |
| Border `#E5EAF0` for form controls | `#8795A8` for control borders | non-text contrast needs 3:1; `#E5EAF0` stays for cards and dividers |

Measured ratios: text primary on canvas 13.1:1; white on navy 11.4:1; white on blue 6.1:1; sidebar text on navy 9.3:1; sidebar muted labels on navy 6.6:1.

## Typography, shape, elevation
- Font stack: Inter if installed, otherwise the system UI font (no web-font download). Sizes: page title `text-xl` (mobile) / `text-2xl`; section title `text-base` semibold; body `text-sm`; captions `text-xs`. AED figures use `.tabular` (tabular numerals).
- Radius: one base `--radius` 0.5rem (`rounded-md` controls, `rounded-xl` cards).
- Elevation: `shadow-card` (hairline) for surfaces, `shadow-pop` for menus, dialogs and the drawer. No gradients, no decorative animation; sidebar width and drawer slide use short transitions that respect `prefers-reduced-motion`.
- Layout tokens: `--sidebar-width` 16rem, `--sidebar-rail-width` 4rem, `--header-height` 3.5rem.

## Sizing and focus
- Controls are 36px high on desktop; header icon buttons, sidebar rows, drawer rows and form actions become 44px on touch widths.
- One focus style: a 2px outline in `--ring` (white on the navy sidebar) on every keyboard-focused control; form inputs use a 2px ring. Never remove an outline without replacing it. (Tailwind v4 note: `outline-none` sets `outline-style: none` and defeats `focus-visible:outline-*`; the end-to-end test now catches this.)
- Status is never colour alone: `StatusBadge` adds a dot and the word.

## Not included
Dark mode, theme switcher, custom fonts, illustration, charts (Recharts is installed; the first chart arrives with the dashboard module).
