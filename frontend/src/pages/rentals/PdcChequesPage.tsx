import {
  AlertTriangle,
  Ban,
  CalendarClock,
  CheckCircle2,
  Clock,
  Landmark,
  Search,
  Wallet,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useChequeSummary, useCheques } from '@/hooks/use-rentals'
import {
  CHEQUE_STATUSES,
  RENTAL_BANKS,
  type Cheque,
  type ChequeStatus,
  type RentalBank,
} from '@/schemas/rentals'
import type { ChequeFilters } from '@/services/rentals.service'
import { formatAED, formatDate } from '@/utils/format'
import { ChequeActions } from './ChequeActions'
import { ChequeBadge, ChequeLink } from './shared'

const PAGE_SIZE = 25
const VIEWS = [
  { value: 'all', label: 'All cheques' },
  { value: 'overdue', label: 'Overdue pending' },
  { value: 'upcoming', label: 'Upcoming pending' },
  { value: 'bounced_open', label: 'Bounced, not replaced' },
] as const
type View = (typeof VIEWS)[number]['value']
const SORTS: { value: string; label: string; sort: ChequeFilters['sort']; desc: boolean }[] = [
  { value: 'date', label: 'Cheque date (oldest first)', sort: 'date', desc: false },
  { value: 'date_desc', label: 'Cheque date (newest first)', sort: 'date', desc: true },
  { value: 'amount', label: 'Highest amount', sort: 'amount', desc: true },
  { value: 'branch', label: 'Branch', sort: 'branch', desc: false },
  { value: 'landlord', label: 'Landlord (A–Z)', sort: 'landlord', desc: false },
]

export function PdcChequesPage() {
  const [params] = useSearchParams()
  const { branches } = useBranchContext()
  const summary = useChequeSummary()
  const initialView = params.get('view')
  const [q, setQ] = useState('')
  const [branch, setBranch] = useState('all')
  const [bank, setBank] = useState('all')
  const [status, setStatus] = useState('all')
  const [view, setView] = useState<string>(
    VIEWS.some((v) => v.value === initialView) ? (initialView as View) : 'all',
  )
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [sortKey, setSortKey] = useState('date')
  const [page, setPage] = useState(1)
  const sort = SORTS.find((s) => s.value === sortKey) ?? SORTS[0]!
  const filters: ChequeFilters = {
    page,
    page_size: PAGE_SIZE,
    sort: sort.sort,
    desc: sort.desc,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(branch !== 'all' ? { branch_id: branch } : {}),
    ...(bank !== 'all' ? { bank: bank as RentalBank } : {}),
    ...(status !== 'all' ? { status: status as ChequeStatus } : {}),
    ...(view !== 'all' ? { view: view as NonNullable<ChequeFilters['view']> } : {}),
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: to } : {}),
  }
  const list = useCheques(filters)
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }
  const s = summary.data
  const next = s?.next_cheque ?? null

  const columns: DataTableColumn<Cheque>[] = [
    { key: 'd', header: 'Cheque date', cell: (r) => formatDate(r.cheque_date) },
    { key: 'n', header: 'Number', cell: (r) => <ChequeLink cheque={r} /> },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name },
    { key: 'l', header: 'Landlord', cell: (r) => r.landlord },
    {
      key: 'ag',
      header: 'Rental agreement',
      cell: (r) => (
        <Link
          to={`/rentals/${r.agreement_id}`}
          className="text-primary underline-offset-4 hover:underline"
        >
          {r.unit ?? 'View agreement'}
        </Link>
      ),
    },
    { key: 'bk', header: 'Bank', cell: (r) => r.bank },
    { key: 'a', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
    { key: 's', header: 'Status', cell: (r) => <ChequeBadge cheque={r} /> },
    { key: 'x', header: 'Actions', cell: (r) => <ChequeActions cheque={r} compact /> },
  ]

  return (
    <PageContainer
      title="PDC Cheques"
      description="Post-dated rent cheques: clear, bounce and replace them. Owner only."
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="PDC summary">
        <StatCard
          label="Total Pending"
          icon={Clock}
          isLoading={summary.isLoading}
          value={s ? String(s.pending_count) : undefined}
        />
        <StatCard
          label="Pending Due Within 30 Days"
          icon={CalendarClock}
          isLoading={summary.isLoading}
          value={s ? String(s.due_30_count) : undefined}
        />
        <StatCard
          label="Overdue Pending"
          icon={AlertTriangle}
          isLoading={summary.isLoading}
          value={s ? String(s.overdue_count) : undefined}
        />
        <StatCard
          label="Cleared"
          icon={CheckCircle2}
          isLoading={summary.isLoading}
          value={s ? String(s.cleared_count) : undefined}
        />
        <StatCard
          label="Bounced"
          icon={Ban}
          isLoading={summary.isLoading}
          value={s ? String(s.bounced_count) : undefined}
        />
        <StatCard
          label="Total Pending Amount"
          icon={Wallet}
          isLoading={summary.isLoading}
          value={s ? formatAED(s.pending_amount) : undefined}
        />
        <StatCard
          label="Total Bounced Amount"
          icon={Landmark}
          isLoading={summary.isLoading}
          value={s ? formatAED(s.bounced_amount) : undefined}
          {...(s && s.bounced_unresolved_count > 0
            ? { description: `${s.bounced_unresolved_count} not yet replaced` }
            : {})}
        />
        <StatCard
          label="Next Upcoming Cheque"
          icon={CalendarClock}
          isLoading={summary.isLoading}
          value={next ? formatDate(next.cheque_date) : s ? 'None' : undefined}
          {...(next
            ? { description: `${next.cheque_no} · ${next.landlord} · ${formatAED(next.amount)}` }
            : {})}
        />
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Quick views">
          {VIEWS.map((v) => (
            <Button
              key={v.value}
              size="sm"
              variant={view === v.value ? 'default' : 'outline'}
              aria-pressed={view === v.value}
              onClick={() => reset(setView)(v.value)}
            >
              {v.label}
            </Button>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <FormInput
              label="Search"
              type="search"
              placeholder="Cheque number, branch or landlord"
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
            label="Bank"
            value={bank}
            onValueChange={reset(setBank)}
            options={[
              { value: 'all', label: 'All banks' },
              ...RENTAL_BANKS.map((b) => ({ value: b, label: b })),
            ]}
          />
          <FormSelect
            label="Status"
            value={status}
            onValueChange={reset(setStatus)}
            options={[
              { value: 'all', label: 'All statuses' },
              ...CHEQUE_STATUSES.map((x) => ({ value: x, label: x })),
            ]}
          />
          <FormDatePicker
            label="Cheque date from"
            value={from}
            onChange={(e) => reset(setFrom)(e.target.value)}
          />
          <FormDatePicker
            label="Cheque date to"
            value={to}
            onChange={(e) => reset(setTo)(e.target.value)}
          />
          <FormSelect
            label="Sort by"
            value={sortKey}
            onValueChange={reset(setSortKey)}
            options={SORTS.map((x) => ({ value: x.value, label: x.label }))}
          />
        </div>
        <SectionCard title="Cheques" contentClassName="p-0 sm:p-0">
          <DataTable
            caption="PDC cheques"
            rows={list.data?.items}
            isLoading={list.isLoading}
            error={list.error}
            onRetry={() => void list.refetch()}
            getRowId={(r) => r.id}
            columns={columns}
            emptyTitle="No cheques found"
            emptyDescription="Cheques appear when a rental agreement is saved. Change the filters to see more."
          />
        </SectionCard>
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="cheques"
            onPage={setPage}
          />
        ) : null}
      </div>
    </PageContainer>
  )
}
