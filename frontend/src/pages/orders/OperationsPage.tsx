import { useState } from 'react'
import { Pagination } from '@/components/common/pagination'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useOpsCounts, useOpsView } from '@/hooks/use-orders'
import { dubaiToday } from '@/utils/format'
import { Can } from '@/auth/permission-guards'
import { DataTable } from '@/components/common/data-table'
import { toast } from 'sonner'
import { useSetStatus } from '@/hooks/use-orders'
import { getErrorMessage } from '@/lib/errors'
import type { OrderRow } from '@/schemas/orders'
import { orderColumns } from './order-columns'

const NEXT: Record<string, string> = {
  New: 'Scheduled',
  Scheduled: 'Picked Up',
  'Picked Up': 'Processing',
  Processing: 'Ready',
  Ready: 'Out for Delivery',
  'Out for Delivery': 'Delivered',
}

/** One-step status update straight from the schedule. The server still validates the move and records who made it. */
function QuickStatus({ order }: { order: OrderRow }) {
  const set = useSetStatus(order.id)
  const next = NEXT[order.status]
  if (!next) return <span className="text-muted-foreground">—</span>
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={set.isPending}
      aria-label={`Mark ${order.order_no} ${next}`}
      onClick={() =>
        set.mutate(
          { status: next },
          {
            onSuccess: () => toast.success(`${order.order_no} marked ${next}`),
            onError: (e) => toast.error(getErrorMessage(e)),
          },
        )
      }
    >
      Mark {next}
    </Button>
  )
}

const OPS_VIEWS: { key: string; label: string; hint: string }[] = [
  {
    key: 'pickups_today',
    label: "Today's Pickups",
    hint: 'Pickups scheduled for the chosen date.',
  },
  {
    key: 'deliveries_today',
    label: "Today's Deliveries",
    hint: 'Deliveries due on the chosen date.',
  },
  {
    key: 'pending_pickups',
    label: 'Pending Pickups',
    hint: 'Scheduled orders waiting to be collected.',
  },
  {
    key: 'overdue_pickups',
    label: 'Overdue Pickups',
    hint: 'Pickup time has passed and the order is not picked up.',
  },
  { key: 'processing', label: 'Processing', hint: 'Picked up and being processed.' },
  { key: 'ready', label: 'Ready', hint: 'Ready for delivery or collection.' },
  { key: 'out_for_delivery', label: 'Out for Delivery', hint: 'On the way to the customer.' },
  {
    key: 'overdue_deliveries',
    label: 'Overdue Deliveries',
    hint: 'Delivery time has passed and the order is not delivered.',
  },
  {
    key: 'incomplete',
    label: 'Unassigned / Incomplete',
    hint: 'Open orders missing a pickup or delivery address, or a pickup time.',
  },
]
const SORTS = [
  { value: 'delivery', label: 'Delivery time' },
  { value: 'pickup', label: 'Pickup time' },
  { value: 'order_no', label: 'Order number' },
  { value: 'customer', label: 'Customer' },
]
const PAGE_SIZE = 25

/** Day-to-day pickup and delivery work. No GPS, routes or live tracking: this is a schedule of orders. */
export function OperationsPage() {
  const { canChoose, selectedBranchId } = useBranchContext()
  const [view, setView] = useState('pickups_today')
  const [day, setDay] = useState(dubaiToday())
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('')
  const [page, setPage] = useState(1)
  const branch_id = canChoose && selectedBranchId !== 'all' ? selectedBranchId : undefined
  const counts = useOpsCounts({ date: day, branch_id })
  const list = useOpsView(view, {
    date: day,
    branch_id,
    q: q.trim(),
    sort: sort || undefined,
    page,
    page_size: PAGE_SIZE,
  })
  const cur = OPS_VIEWS.find((v) => v.key === view)

  return (
    <PageContainer
      title="Pickup & Delivery"
      description="Today's pickups and deliveries, and the orders that need attention. Dubai time."
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <FormDatePicker
          label="Date"
          value={day}
          onChange={(e) => {
            setDay(e.target.value)
            setPage(1)
          }}
        />
        <FormInput
          label="Search"
          type="search"
          placeholder="Order number, name or mobile"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setPage(1)
          }}
          maxLength={100}
        />
        <FormSelect
          label="Sort by"
          value={sort || 'delivery'}
          options={SORTS}
          onValueChange={(v) => {
            setSort(v)
            setPage(1)
          }}
        />
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Operations views">
        {OPS_VIEWS.map((v) => (
          <Button
            key={v.key}
            role="tab"
            size="sm"
            aria-selected={view === v.key}
            variant={view === v.key ? 'default' : 'outline'}
            onClick={() => {
              setView(v.key)
              setPage(1)
            }}
          >
            {v.label}
            <span className="tabular ml-1 rounded-full bg-black/10 px-1.5 text-xs">
              {counts.data?.[v.key] ?? '–'}
            </span>
          </Button>
        ))}
      </div>
      {cur ? <p className="text-sm text-muted-foreground">{cur.hint}</p> : null}

      <DataTable
        columns={[
          ...orderColumns({ showBranch: canChoose }),
          {
            key: 'action',
            header: 'Update',
            cell: (o: OrderRow) => (
              <Can module="orders" action="update">
                <QuickStatus order={o} />
              </Can>
            ),
          },
        ]}
        getRowId={(o: OrderRow) => o.id}
        rows={list.data?.items}
        caption={cur?.label ?? 'Orders'}
        isLoading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        emptyTitle="Nothing in this view"
        emptyDescription="Orders appear here as their pickup and delivery times come up."
      />
      {list.data ? (
        <Pagination
          page={list.data.page}
          pageSize={list.data.page_size}
          total={list.data.total}
          noun="orders"
          onPage={setPage}
        />
      ) : null}
    </PageContainer>
  )
}
