import { useMemo } from 'react'
import { usePermissions } from '@/auth/use-permissions'
import { NAV_SECTIONS, type NavItem, type NavSection } from '@/config/navigation'

/** The navigation the signed-in user may see: only permitted items, no empty sections or groups. */
export function useNavigation(): NavSection[] {
  const { can, scope } = usePermissions()
  return useMemo(() => {
    const allowed = (item: NavItem) =>
      can(item.module, item.action) &&
      (item.requireScope === undefined || scope(item.module) === item.requireScope)
    const visible = (item: NavItem): NavItem | null => {
      if (item.children) {
        const children = item.children.filter(allowed)
        return children.length > 0 ? { ...item, children } : null
      }
      return allowed(item) ? item : null
    }
    return NAV_SECTIONS.map((section) => ({
      ...section,
      items: section.items.map(visible).filter((i): i is NavItem => i !== null),
    })).filter((section) => section.items.length > 0)
  }, [can, scope])
}

/** Presentation variant, derived from the server-sent dashboard scope (never from a role name). */
export function useLayoutVariant(): 'owner' | 'branch' {
  const { scope } = usePermissions()
  return scope('dashboard') === 'all_branches' ? 'owner' : 'branch'
}
