import { Plus, Search, Truck, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { StatCard } from '@/components/common/stat-card'
import { StatusBadge } from '@/components/common/status-badge'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useBalances, useSupplierSummary, useSuppliers } from '@/hooks/use-finance'
import type { SupplierFilters } from '@/services/finance.service'
import type { Supplier } from '@/schemas/finance'
import { formatAED } from '@/utils/format'
import { SupplierDialog } from './SupplierDialog'

const PAGE_SIZE = 25

const SORTS: { value: string; label: string; sort: SupplierFilters['sort']; desc: boolean }[] = [
  { value: 'name', label: 'Name (A–Z)', sort: 'name', desc: false },
  { value: 'outstanding', label: 'Highest outstanding', sort: 'outstanding', desc: true },
  { value: 'paid', label: 'Most paid', sort: 'paid', desc: true },
  { value: 'created', label: 'Newest first', sort: 'created', desc: true },
]

export function SuppliersPage() {
  const summary = useSupplierSummary()
  const balances = useBalances()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<'all' | 'active' | 'inactive'>('all')
  const [owing, setOwing] = useState('all')
  const [sortKey, setSortKey] = useState('name')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const sort = SORTS.find((s) => s.value === sortKey) ?? SORTS[0]!

  const filters: SupplierFilters = {
    page,
    page_size: PAGE_SIZE,
    sort: sort.sort,
    desc: sort.desc,
    status,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(owing === 'owing' ? { outstanding_only: true } : {}),
  }
  const list = useSuppliers(filters)
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }
  const s = summary.data

  const columns: DataTableColumn<Supplier>[] = [
    {
      key: 'n',
      header: 'Supplier',
      cell: (r) => (
        <Link
          to={`/suppliers/${r.id}`}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {r.name}
        </Link>
      ),
    },
    { key: 'c', header: 'Supplies / service', cell: (r) => r.category ?? '—' },
    { key: 't', header: 'Payment terms', cell: (r) => r.payment_terms ?? '—' },
    {
      key: 'o',
      header: 'Outstanding',
      align: 'right',
      cell: (r) => <strong>{formatAED(r.outstanding)}</strong>,
    },
    { key: 'p', header: 'Paid', align: 'right', cell: (r) => formatAED(r.total_paid) },
    {
      key: 's',
      header: 'Status',
      cell: (r) =>
        r.is_active ? (
          <StatusBadge status="success">Active</StatusBadge>
        ) : (
          <StatusBadge status="neutral">Inactive</StatusBadge>
        ),
    },
  ]

  return (
    <PageContainer
      title="Suppliers"
      description="Who you owe, what has been paid, and the history behind it."
      actions={
        <Can module="suppliers" action="create">
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden /> Add supplier
          </Button>
        </Can>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Supplier summary">
        <StatCard
          label="Total Suppliers"
          icon={Users}
          isLoading={summary.isLoading}
          value={s ? String(s.total_suppliers) : undefined}
        />
        <StatCard
          label="Total Outstanding"
          icon={Truck}
          isLoading={summary.isLoading}
          value={s ? formatAED(s.total_outstanding) : undefined}
        />
        <StatCard
          label="Total Paid"
          isLoading={summary.isLoading}
          value={s ? formatAED(s.total_paid) : undefined}
        />
        <StatCard
          label="Suppliers with Dues"
          isLoading={summary.isLoading}
          value={s ? String(s.with_outstanding) : undefined}
        />
      </div>

      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <FormInput
              label="Search"
              type="search"
              placeholder="Name or description"
              value={q}
              onChange={(e) => reset(setQ)(e.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 bottom-2.5 size-4 text-muted-foreground"
              aria-hidden
            />
          </div>
          <FormSelect
            label="Status"
            value={status}
            onValueChange={(v) => reset(setStatus)(v as typeof status)}
            options={[
              { value: 'all', label: 'All' },
              { value: 'active', label: 'Active' },
              { value: 'inactive', label: 'Inactive' },
            ]}
          />
          <FormSelect
            label="Dues"
            value={owing}
            onValueChange={reset(setOwing)}
            options={[
              { value: 'all', label: 'All suppliers' },
              { value: 'owing', label: 'With outstanding dues' },
            ]}
          />
          <FormSelect
            label="Sort by"
            value={sortKey}
            onValueChange={reset(setSortKey)}
            options={SORTS.map((x) => ({ value: x.value, label: x.label }))}
          />
        </div>
        <DataTable
          caption="Suppliers"
          rows={list.data?.items}
          isLoading={list.isLoading}
          error={list.error}
          onRetry={() => void list.refetch()}
          getRowId={(r) => r.id}
          columns={columns}
          emptyTitle="No suppliers found"
          emptyDescription="Add a supplier, or change the search and filters."
        />
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="suppliers"
            onPage={setPage}
          />
        ) : null}
      </div>

      <SupplierDialog
        open={adding}
        onOpenChange={setAdding}
        openingEditable={balances.data?.status === 'not_configured'}
      />
    </PageContainer>
  )
}
