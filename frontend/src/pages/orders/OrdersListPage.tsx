import { PackagePlus, Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { Pagination } from '@/components/common/pagination'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useCategories, useOrders } from '@/hooks/use-orders'
import { ORDER_STATUSES, PAYMENT_STATUSES, SERVICE_TYPES } from '@/schemas/orders'
import { OrderTable } from './order-ui'

const ALL = 'all'
const opt = (v: readonly string[]) => [
  { value: ALL, label: 'All' },
  ...v.map((x) => ({ value: x, label: x })),
]
const SORTS = [
  { value: 'created', label: 'Newest first' },
  { value: 'order_no', label: 'Order number' },
  { value: 'order_date', label: 'Order date' },
  { value: 'pickup', label: 'Pickup time' },
  { value: 'delivery', label: 'Delivery time' },
  { value: 'customer', label: 'Customer' },
  { value: 'status', label: 'Status' },
  { value: 'amount', label: 'Amount' },
  { value: 'outstanding', label: 'Outstanding' },
]
const PAGE_SIZE = 25

/** Search and filter every order the signed-in user may see (Owner: all branches; Branch User: own branch). */
export function OrdersListPage() {
  const { canChoose, selectedBranchId, branches } = useBranchContext()
  const cats = useCategories()
  const [f, setF] = useState({
    q: '',
    status: ALL,
    payment_status: ALL,
    category_id: ALL,
    service_type: ALL,
    area: '',
    date_from: '',
    date_to: '',
    pickup_date: '',
    delivery_date: '',
    branch: ALL,
    sort: 'created',
  })
  const [page, setPage] = useState(1)
  const set = (patch: Partial<typeof f>) => {
    setF((s) => ({ ...s, ...patch }))
    setPage(1)
  }
  const branch = canChoose ? (f.branch !== ALL ? f.branch : selectedBranchId) : ALL
  const list = useOrders({
    q: f.q,
    status: f.status,
    payment_status: f.payment_status,
    category_id: f.category_id,
    service_type: f.service_type,
    area: f.area,
    date_from: f.date_from,
    date_to: f.date_to,
    pickup_date: f.pickup_date,
    delivery_date: f.delivery_date,
    branch_id: branch,
    sort: f.sort,
    desc: f.sort === 'created' || f.sort === 'amount' || f.sort === 'outstanding',
    page,
    page_size: PAGE_SIZE,
  })
  const bad = Boolean(f.date_from && f.date_to && f.date_from > f.date_to)

  return (
    <PageContainer
      title="Orders"
      description="Search by order number, customer name or mobile, then narrow with filters."
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
      <form
        role="search"
        aria-label="Order filters"
        className="space-y-3 rounded-xl border bg-card p-4 shadow-card"
        onSubmit={(e) => e.preventDefault()}
      >
        <FormInput
          label="Search orders"
          type="search"
          placeholder="Order number, customer name or mobile"
          value={f.q}
          onChange={(e) => set({ q: e.target.value })}
          maxLength={100}
        />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <FormSelect
            label="Order status"
            value={f.status}
            options={opt(ORDER_STATUSES)}
            onValueChange={(v) => set({ status: v })}
          />
          <FormSelect
            label="Payment status"
            value={f.payment_status}
            options={opt(PAYMENT_STATUSES)}
            onValueChange={(v) => set({ payment_status: v })}
          />
          <FormSelect
            label="Service category"
            value={f.category_id}
            options={[
              { value: ALL, label: 'All' },
              ...(cats.data ?? []).map((c) => ({ value: c.id, label: c.name })),
            ]}
            onValueChange={(v) => set({ category_id: v })}
          />
          <FormSelect
            label="Service type"
            value={f.service_type}
            options={opt(SERVICE_TYPES)}
            onValueChange={(v) => set({ service_type: v })}
          />
          <FormDatePicker
            label="Order date from"
            value={f.date_from}
            onChange={(e) => set({ date_from: e.target.value })}
          />
          <FormDatePicker
            label="Order date to"
            value={f.date_to}
            min={f.date_from || undefined}
            onChange={(e) => set({ date_to: e.target.value })}
          />
          <FormDatePicker
            label="Pickup date"
            value={f.pickup_date}
            onChange={(e) => set({ pickup_date: e.target.value })}
          />
          <FormDatePicker
            label="Delivery date"
            value={f.delivery_date}
            onChange={(e) => set({ delivery_date: e.target.value })}
          />
          <FormInput
            label="Area"
            value={f.area}
            onChange={(e) => set({ area: e.target.value })}
            maxLength={100}
          />
          {canChoose ? (
            <FormSelect
              label="Branch"
              value={f.branch !== ALL ? f.branch : selectedBranchId}
              options={[
                { value: ALL, label: 'All Branches' },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
              onValueChange={(v) => set({ branch: v })}
            />
          ) : null}
          <FormSelect
            label="Sort by"
            value={f.sort}
            options={SORTS}
            onValueChange={(v) => set({ sort: v })}
          />
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setF((s) => ({
                ...s,
                q: '',
                status: ALL,
                payment_status: ALL,
                category_id: ALL,
                service_type: ALL,
                area: '',
                date_from: '',
                date_to: '',
                pickup_date: '',
                delivery_date: '',
                branch: ALL,
              }))
              setPage(1)
            }}
          >
            <Search aria-hidden /> Clear filters
          </Button>
        </div>
        {bad ? (
          <p role="alert" className="text-sm text-destructive">
            The start date must be on or before the end date.
          </p>
        ) : null}
      </form>

      <OrderTable
        rows={bad ? [] : list.data?.items}
        caption="Orders"
        isLoading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        showBranch={canChoose}
        emptyTitle="No orders match"
        emptyDescription="Change the filters or search, or create a new order."
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
