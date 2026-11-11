import { BarChart3, Home, MoreHorizontal, Package, Plus, type LucideIcon } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import { usePermissions } from '@/auth/use-permissions'
import { cn } from '@/lib/utils'

interface Tab {
  to: string
  label: string
  icon: LucideIcon
}

function TabLink({ to, label, icon: Icon, active }: Tab & { active: boolean }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={cn(
        'flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] font-medium transition-colors',
        active ? 'bg-sky-100 text-accent' : 'text-muted-foreground hover:text-primary',
      )}
    >
      <Icon className="size-5" aria-hidden />
      {label}
    </NavLink>
  )
}

/**
 * Phone-only tab bar: Dashboard, Orders, a central "new order" button, Reports and More (the full menu).
 * Every tab uses the same module/action pair as its route guard, so a visible tab is always an allowed page.
 */
export function MobileBottomNav() {
  const { pathname } = useLocation()
  const { can } = usePermissions()
  const isActive = (to: string) =>
    to === '/' ? pathname === '/' : pathname === to || pathname.startsWith(`${to}/`)

  const left: Tab[] = [
    ...(can('dashboard', 'read') ? [{ to: '/', label: 'Dashboard', icon: Home }] : []),
    ...(can('orders', 'read') ? [{ to: '/orders', label: 'Orders', icon: Package }] : []),
  ]
  const reports: Tab | null = can('reports', 'read')
    ? { to: '/reports', label: 'Reports', icon: BarChart3 }
    : can('daily_reports', 'read')
      ? { to: '/daily-reports', label: 'Reports', icon: BarChart3 }
      : null
  const right: Tab[] = [
    ...(reports ? [reports] : []),
    { to: '/more', label: 'More', icon: MoreHorizontal },
  ]
  const canCreateOrder = can('orders', 'create')

  return (
    <nav
      aria-label="Quick navigation"
      className="fixed inset-x-0 bottom-0 z-30 flex items-center gap-1 rounded-t-2xl border-t bg-card px-2 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-pop"
    >
      {left.map((t) => (
        <TabLink key={t.to} {...t} active={isActive(t.to)} />
      ))}
      {canCreateOrder ? (
        <NavLink
          to="/orders/new"
          aria-label="New order"
          className="-mt-8 grid size-14 shrink-0 place-items-center rounded-full bg-accent text-white shadow-lg ring-4 ring-card"
        >
          <Plus className="size-7" aria-hidden />
        </NavLink>
      ) : null}
      {right.map((t) => (
        <TabLink key={t.to} {...t} active={isActive(t.to)} />
      ))}
    </nav>
  )
}
