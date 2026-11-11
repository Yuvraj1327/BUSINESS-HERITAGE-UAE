import { BarChart3, Package, PlusSquare, Receipt, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { SectionCard } from '@/components/common/section-card'
import type { AppAction, AppModule } from '@/auth/permissions'
import { usePermissions } from '@/auth/use-permissions'
import { cn } from '@/lib/utils'

interface QuickAction {
  label: string
  to: string
  icon: LucideIcon
  module: AppModule
  action: AppAction
  tone: string
}

// Same routes and module/action pairs the router guards use, so a shown shortcut is always an allowed page.
const ACTIONS: QuickAction[] = [
  {
    label: 'Add Order',
    to: '/orders/new',
    icon: PlusSquare,
    module: 'orders',
    action: 'create',
    tone: 'bg-sky-100 text-sky-800',
  },
  {
    label: 'Daily Report',
    to: '/daily-reports',
    icon: BarChart3,
    module: 'daily_reports',
    action: 'read',
    tone: 'bg-emerald-100 text-emerald-800',
  },
  {
    label: 'Add Expense',
    to: '/expenses',
    icon: Receipt,
    module: 'expenses',
    action: 'read',
    tone: 'bg-orange-100 text-orange-800',
  },
  {
    label: 'View Orders',
    to: '/orders',
    icon: Package,
    module: 'orders',
    action: 'read',
    tone: 'bg-violet-100 text-violet-800',
  },
]

export function QuickActions({ className }: { className?: string }) {
  const { can } = usePermissions()
  const visible = ACTIONS.filter((a) => can(a.module, a.action))
  if (visible.length === 0) return null
  return (
    <SectionCard title="Quick Actions" className={className}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
        {visible.map(({ label, to, icon: Icon, tone }) => (
          <Link
            key={to}
            to={to}
            className={cn(
              'flex min-h-24 flex-col items-center justify-center gap-2 rounded-xl p-3 text-center text-sm font-medium transition hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
              tone,
            )}
          >
            <Icon className="size-6" aria-hidden />
            {label}
          </Link>
        ))}
      </div>
    </SectionCard>
  )
}
