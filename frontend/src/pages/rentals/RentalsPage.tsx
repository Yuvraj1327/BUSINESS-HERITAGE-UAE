import { AlertTriangle, CalendarClock, FileClock, Home, Plus, Search, Wallet } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useAgreements, useRentalSummary, useUpcomingExpiries } from '@/hooks/use-rentals'
import { AGREEMENT_STATUSES, type Agreement, type AgreementStatus } from '@/schemas/rentals'
import type { AgreementFilters } from '@/services/rentals.service'
import { formatAED, formatDate } from '@/utils/format'
import { AgreementDialog } from './AgreementDialog'
import { endText } from './helpers'
import { AgreementBadge } from './shared'

const PAGE_SIZE = 25
const SORTS: { value: string; label: string; sort: AgreementFilters['sort']; desc: boolean }[] = [
  { value: 'end', label: 'End date (soonest first)', sort: 'end', desc: false },
  { value: 'end_desc', label: 'End date (latest first)', sort: 'end', desc: true },
  { value: 'branch', label: 'Branch', sort: 'branch', desc: false },
  { value: 'landlord', label: 'Landlord (A–Z)', sort: 'landlord', desc: false },
  { value: 'rent', label: 'Highest rent', sort: 'rent', desc: true },
]

export function RentalsPage() {
  const navigate = useNavigate()
  const { branches } = useBranchContext()
  const summary = useRentalSummary()
  const upcoming = useUpcomingExpiries()
  const [q, setQ] = useState('')
  const [branch, setBranch] = useState('all')
  const [status, setStatus] = useState('all')
  const [sortKey, setSortKey] = useState('end')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const sort = SORTS.find((s) => s.value === sortKey) ?? SORTS[0]!
  const filters: AgreementFilters = {
    page,
    page_size: PAGE_SIZE,
    sort: sort.sort,
    desc: sort.desc,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(branch !== 'all' ? { branch_id: branch } : {}),
    ...(status !== 'all' ? { status: status as AgreementStatus } : {}),
  }
  const list = useAgreements(filters)
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }
  const s = summary.data

  const columns: DataTableColumn<Agreement>[] = [
    {
      key: 'b',
      header: 'Branch',
      cell: (r) => (
        <Link
          to={`/rentals/${r.id}`}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {r.branch_name}
        </Link>
      ),
    },
    { key: 'l', header: 'Landlord', cell: (r) => r.landlord },
    { key: 'u', header: 'Unit', cell: (r) => r.unit ?? '—' },
    {
      key: 'p',
      header: 'Period',
      cell: (r) => `${formatDate(r.start_date)} – ${formatDate(r.end_date)}`,
    },
    { key: 'a', header: 'Annual rent', align: 'right', cell: (r) => formatAED(r.annual_rent) },
    {
      key: 'c',
      header: 'Cheques',
      cell: (r) =>
        `${r.cleared_count} cleared · ${r.pending_count} pending${r.bounced_count ? ` · ${r.bounced_count} bounced` : ''}`,
    },
    {
      key: 's',
      header: 'Status',
      cell: (r) => (
        <span className="inline-flex flex-wrap items-center gap-2">
          <AgreementBadge status={r.status} />
          {r.status === 'Active' || r.status === 'Expiring' || r.status === 'Expired' ? (
            <span className="text-xs text-muted-foreground">{endText(r.days_to_end)}</span>
          ) : null}
        </span>
      ),
    },
  ]
  const upcomingColumns: DataTableColumn<Agreement>[] = [
    {
      key: 'b',
      header: 'Branch',
      cell: (r) => (
        <Link to={`/rentals/${r.id}`} className="font-medium text-primary hover:underline">
          {r.branch_name}
        </Link>
      ),
    },
    { key: 'l', header: 'Landlord', cell: (r) => r.landlord },
    { key: 'e', header: 'Ends', cell: (r) => formatDate(r.end_date) },
    { key: 'd', header: 'Time left', cell: (r) => endText(r.days_to_end) },
    { key: 's', header: 'Status', cell: (r) => <AgreementBadge status={r.status} /> },
  ]

  return (
    <PageContainer
      title="Rental Agreements"
      description="Shop and property rentals with their PDC cheque schedules. Owner only."
      actions={
        <Can module="rentals_cheques" action="create">
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden /> Add agreement
          </Button>
        </Can>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Rental summary">
        <StatCard
          label="Active agreements"
          icon={Home}
          isLoading={summary.isLoading}
          value={s ? String(s.agreements_active) : undefined}
        />
        <StatCard
          label="Ending within 30 days"
          icon={CalendarClock}
          isLoading={summary.isLoading}
          value={s ? String(s.expiring_30) : undefined}
          description={s ? `${s.renewal_approaching} more end in 31 to 90 days` : undefined}
        />
        <StatCard
          label="Ended, not renewed"
          icon={AlertTriangle}
          isLoading={summary.isLoading}
          value={s ? String(s.expired_unrenewed) : undefined}
        />
        <StatCard
          label="Annual rent (active)"
          icon={Wallet}
          isLoading={summary.isLoading}
          value={s ? formatAED(s.annual_rent_active) : undefined}
        />
      </div>

      <SectionCard
        title="Upcoming expiries"
        description="Agreements ending within 90 days, soonest first."
        actions={
          <Button variant="outline" size="sm" asChild>
            <Link to="/pdc-cheques">
              <FileClock aria-hidden /> PDC Cheques
            </Link>
          </Button>
        }
      >
        <DataTable
          caption="Upcoming expiries"
          rows={upcoming.data?.items}
          isLoading={upcoming.isLoading}
          error={upcoming.error}
          onRetry={() => void upcoming.refetch()}
          getRowId={(r) => r.id}
          columns={upcomingColumns}
          emptyTitle="No agreement ends in the next 90 days"
        />
      </SectionCard>

      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <FormInput
              label="Search"
              type="search"
              placeholder="Branch, landlord or unit"
              value={q}
              onChange={(e) => reset(setQ)(e.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 bottom-2.5 size-4 text-muted-foreground"
              aria-hidden
            />
          </div>
          <FormSelect
            label="Branch"
            value={branch}
            onValueChange={reset(setBranch)}
            options={[
              { value: 'all', label: 'All branches' },
              ...branches.map((b) => ({ value: b.id, label: b.name })),
            ]}
          />
          <FormSelect
            label="Status"
            value={status}
            onValueChange={reset(setStatus)}
            options={[
              { value: 'all', label: 'All statuses' },
              ...AGREEMENT_STATUSES.map((x) => ({ value: x, label: x })),
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
          caption="Rental agreements"
          rows={list.data?.items}
          isLoading={list.isLoading}
          error={list.error}
          onRetry={() => void list.refetch()}
          getRowId={(r) => r.id}
          columns={columns}
          emptyTitle="No rental agreements found"
          emptyDescription="Add an agreement, or change the search and filters."
        />
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="agreements"
            onPage={setPage}
          />
        ) : null}
      </div>

      <AgreementDialog
        open={adding}
        onOpenChange={setAdding}
        onSaved={(id) => navigate(`/rentals/${id}`)}
      />
    </PageContainer>
  )
}
