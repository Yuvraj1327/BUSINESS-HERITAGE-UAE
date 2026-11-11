import { EXTRA_PAGES, NAV_SECTIONS, type NavSection } from '@/config/navigation'

export interface Crumb {
  label: string
  /** Absent for the current page and for section labels (sections are not pages). */
  to?: string
}

/** Home → section → (group) → page, derived from the navigation definition so the two never drift apart. */
export function buildBreadcrumbs(pathname: string, sections: NavSection[] = NAV_SECTIONS): Crumb[] {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  if (path === '/') return [{ label: 'Dashboard' }]
  const home: Crumb = { label: 'Dashboard', to: '/' }
  for (const section of sections) {
    for (const item of section.items) {
      if (item.to && matches(path, item.to)) {
        return [home, { label: section.label }, { label: item.label }]
      }
      for (const child of item.children ?? []) {
        if (child.to && matches(path, child.to)) {
          return [home, { label: section.label }, { label: item.label }, { label: child.label }]
        }
      }
    }
  }
  const extra = EXTRA_PAGES[path]
  if (extra) return [home, { label: extra.section }, { label: extra.label }]
  return [home, { label: 'Page not found' }]
}

function matches(path: string, to: string): boolean {
  return to === '/' ? path === '/' : path === to || path.startsWith(`${to}/`)
}
