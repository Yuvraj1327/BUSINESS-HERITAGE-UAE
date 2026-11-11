import { Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { StatCard } from '@/components/common/stat-card'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useLicenses, useLicenseSummary } from '@/hooks/use-hr'
import type { License } from '@/schemas/hr'
import type { LicenseFilters } from '@/services/hr.service'
import { formatAED, formatDate } from '@/utils/format'
import { LicenseDialog } from './LicenseDialog'
import { ExpiryBadge } from './shared'

const PAGE_SIZE = 25
const SORTS: { value: string; label: string; sort: LicenseFilters['sort']; desc: boolean }[] = [
  { value: 'expiry', label: 'Nearest expiry first', sort: 'expiry', desc: false },
  { value: 'expiry-desc', label: 'Latest expiry first', sort: 'expiry', desc: true },
  { value: 'branch', label: 'Branch', sort: 'branch', desc: false },
  { value: 'number', label: 'Licence number', sort: 'number', desc: false },
  { value: 'fee', label: 'Highest fee', sort: 'fee', desc: true },
]

export function TradeLicensesPage() {
  const navigate = useNavigate()
  const { branches } = useBranchContext()
  const summary = useLicenseSummary()
  const [q, setQ] = useState('')
  const [branch, setBranch] = useState('all')
  const [status, setStatus] = useState('all')
  const [sortKey, setSortKey] = useState('expiry')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const sort = SORTS.find((s) => s.value === sortKey) ?? SORTS[0]!
  const list = useLicenses({
    page,
    page_size: PAGE_SIZE,
    sort: sort.sort,
    desc: sort.desc,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(branch !== 'all' ? { branch_id: branch } : {}),
    ...(status !== 'all' ? { status } : {}),
  })
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }
  const s = summary.data
  const n = (v: number | undefined) => (v === undefined ? undefined : String(v))

  const columns: DataTableColumn<License>[] = [
    {
      key: 'b',
      header: 'Branch',
      cell: (r) => (
        <Link
          to={`/trade-licenses/${r.id}`}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {r.branch_name}
        </Link>
      ),
    },
    { key: 'n', header: 'Licence no.', cell: (r) => r.license_no },
    { key: 'a', header: 'Authority', cell: (r) => r.authority ?? '—' },
    { key: 'e', header: 'Expiry', cell: (r) => formatDate(r.expiry_date) },
    {
      key: 's',
      header: 'Status',
      cell: (r) => <ExpiryBadge status={r.status} days={r.days_remaining} />,
    },
    { key: 'f', header: 'Renewal fee', align: 'right', cell: (r) => formatAED(r.renewal_fee) },
    { key: 'r', header: 'Renewals', align: 'right', cell: (r) => r.renewal_count },
  ]

  return (
    <PageContainer
      title="Trade Licenses"
      description="Expiry, renewal fees and renewal history for each branch. Owner only."
      actions={
        <Can module="trade_licenses" action="create">
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden /> Add licence
          </Button>
        </Can>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5" aria-label="Licence summary">
        <StatCard label="Total Licenses" isLoading={summary.isLoading} value={n(s?.total)} />
        <StatCard label="Expired" isLoading={summary.isLoading} value={n(s?.expired)} />
        <StatCard
          label="Expiring ≤ 30 Days"
          isLoading={summary.isLoading}
          value={n(s?.expiring_30)}
        />
        <StatCard
          label="Expiring ≤ 60 Days"
          isLoading={summary.isLoading}
          value={n(s?.expiring_60)}
        />
        <StatCard
          label="Renewal Fees Due"
          isLoading={summary.isLoading}
          value={s ? formatAED(s.renewal_fees_due) : undefined}
          description={
            s ? `${s.fees_due_count} licences expired or expiring within 90 days` : undefined
          }
        />
      </div>

      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <FormInput
              label="Search"
              type="search"
              placeholder="Branch, number or authority"
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
            label="Expiry status"
            value={status}
            onValueChange={reset(setStatus)}
            options={[
              { value: 'all', label: 'All licences' },
              { value: 'expired', label: 'Expired' },
              { value: 'urgent', label: 'Urgent (within 30 days)' },
              { value: 'upcoming', label: 'Upcoming (31–90 days)' },
              { value: 'normal', label: 'Valid' },
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
          caption="Trade licences"
          rows={list.data?.items}
          isLoading={list.isLoading}
          error={list.error}
          onRetry={() => void list.refetch()}
          getRowId={(r) => r.id}
          columns={columns}
          emptyTitle="No trade licences found"
          emptyDescription="Add a licence, or change the search and filters."
        />
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="licences"
            onPage={setPage}
          />
        ) : null}
      </div>

      <LicenseDialog
        open={adding}
        onOpenChange={setAdding}
        onSaved={(id) => navigate(`/trade-licenses/${id}`)}
      />
    </PageContainer>
  )
}
