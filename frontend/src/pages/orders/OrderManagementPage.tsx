import {
  Banknote,
  CalendarCheck,
  PackageCheck,
  PackagePlus,
  ShoppingBag,
  Truck,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useOrderDashboard } from '@/hooks/use-orders'
import { dubaiToday } from '@/utils/format'
import { aed } from './order-format'
import { OrderTable } from './order-ui'

/** Order Management dashboard: today's work first, then everything that needs attention. */
export function OrderManagementPage() {
  const { selectedBranchId, canChoose } = useBranchContext()
  const [day, setDay] = useState(dubaiToday())
  const branch_id = canChoose && selectedBranchId !== 'all' ? selectedBranchId : undefined
  const q = useOrderDashboard({ date: day, branch_id })
  const k = q.data?.kpis

  return (
    <PageContainer
      title="Order Management"
      description="Pickups, deliveries and payments for customer orders. Dubai time."
      actions={
        <Can module="orders" action="create">
          <Button asChild>
            <Link to="/orders/new">
              <PackagePlus aria-hidden /> New Order
            </Link>
          </Button>
        </Can>
      }
    >
      <div className="flex flex-wrap items-end gap-3">
        <FormDatePicker
          label="Schedule date"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
        <Button variant="outline" asChild>
          <Link to="/orders">All orders</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to="/order-operations">Pickup &amp; delivery</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to="/customers">Customers</Link>
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5" aria-label="Key figures">
        <StatCard
          label="Total Orders"
          icon={ShoppingBag}
          isLoading={q.isLoading}
          value={k ? String(k.total_orders) : undefined}
        />
        <StatCard
          label="Today's Pickups"
          icon={PackageCheck}
          isLoading={q.isLoading}
          value={k ? String(k.todays_pickups) : undefined}
        />
        <StatCard
          label="Today's Deliveries"
          icon={Truck}
          isLoading={q.isLoading}
          value={k ? String(k.todays_deliveries) : undefined}
        />
        <StatCard
          label="Monthly Revenue"
          icon={CalendarCheck}
          isLoading={q.isLoading}
          value={k ? aed(k.monthly_revenue) : undefined}
          description="Orders placed this month, excluding cancelled"
        />
        <StatCard
          label="Outstanding Payments"
          icon={Banknote}
          isLoading={q.isLoading}
          value={k ? aed(k.outstanding_payments) : undefined}
          description="All orders except cancelled"
        />
      </div>

      {q.isError ? (
        <p role="alert" className="text-sm text-destructive">
          The dashboard could not be loaded.{' '}
          <Button variant="link" className="h-auto p-0" onClick={() => void q.refetch()}>
            Try again
          </Button>
        </p>
      ) : null}

      {(
        q.data?.sections ??
        (q.isLoading ? [{ key: 'loading', title: 'Loading…', count: 0, items: [] }] : [])
      ).map((s) => (
        <SectionCard
          key={s.key}
          title={s.title}
          description={`${s.count} order${s.count === 1 ? '' : 's'}`}
        >
          <OrderTable
            rows={s.items}
            caption={s.title}
            isLoading={q.isLoading}
            showBranch={canChoose}
            emptyTitle="Nothing here"
            emptyDescription="No orders in this group right now."
          />
        </SectionCard>
      ))}
    </PageContainer>
  )
}
