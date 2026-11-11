# RESPONSIVE_LAYOUT

Layout mode comes from `useLayoutMode()` (`matchMedia`, so React and CSS agree and there is no first-paint flicker):

| Mode | Width | Navigation | Toggle button does |
|---|---|---|---|
| desktop | ≥ 1024px | fixed sidebar 16rem, collapsible to a 4rem icon rail; choice remembered in `localStorage` | collapse / expand |
| tablet | 768–1023px | icon rail (4rem), tooltips; content padded by 4rem | opens the full navigation as a drawer |
| mobile | < 768px | no sidebar; drawer (max 18rem / 85% width) with the same menu | opens the drawer |

## Details
- Content padding follows the mode (`--sidebar-width` / `--sidebar-rail-width` / none); `main` has `min-w-0` so wide children cannot stretch the page.
- Header: toggle, breadcrumbs (phones show only the current page), branch control (Owner selector / Branch User label), date from 1280px up, bell, avatar (name + role from 1024px up). On phones the branch control moves to its own row under the header.
- Drawer: Radix dialog (focus trap, Escape, scroll lock). It closes on navigation and returns focus to the toggle button. Rows, header buttons and form actions are 44px high on touch widths.
- Icon rail: labels stay in the accessibility tree (`sr-only`) and show as tooltips on hover and keyboard focus; section titles become thin rules; the Settings group becomes one link to its first page.
- Page content: `PageContainer` `max-w-7xl`, padding 16px (phone) → 24px → 32px; dashboard grids go 1 → 2 → 4 columns; `DataTable` scrolls horizontally **inside** its own box; forms are single-column and readable down to 360px.
- Accessibility: skip link to `#main-content`, landmarks (`aside`, `nav` "Main" and "Breadcrumb", `header`, `main`), visible focus ring, `prefers-reduced-motion` honoured.
- No page-level horizontal overflow: verified in a real browser at every size below (`document.documentElement.scrollWidth <= innerWidth`).

## Verified viewports
1440×900, 1280×800, 768×1024, 390×844, 360×740, as Owner and as Branch User. See `UI_TEST_RESULTS.md`.

## Known limits
Landscape phones (≥ 768px wide, < 500px tall) use the tablet rail, whose navigation scrolls inside the rail. Very long navigation on short desktop windows scrolls inside the sidebar (the brand and user/sign-out areas stay fixed).
