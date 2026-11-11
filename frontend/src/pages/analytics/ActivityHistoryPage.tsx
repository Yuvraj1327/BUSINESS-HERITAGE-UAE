import { useState } from 'react'
import { SectionCard } from '@/components/common/section-card'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useActors, useReport } from '@/hooks/use-analytics'
import type { ReportFilters } from '@/services/analytics.service'
import { dubaiToday } from '@/utils/format'
import { ReportFilterBar, type FilterState } from './ReportFilterBar'
import { ExportButtons, ReportTable } from './ReportTable'
import { rangeFor, type RangeKey } from './ranges'

const MODULES = [
  ['daily_reports', 'Daily Reports'],
  ['expenses', 'Expenses & Savings'],
  ['suppliers', 'Suppliers'],
  ['cash_banks', 'Cash & Banks'],
  ['opening_balances', 'Opening Balances'],
  ['employees', 'Employees'],
  ['trade_licenses', 'Trade Licenses'],
  ['rentals', 'Rental Agreements'],
  ['pdc_cheques', 'PDC Cheques'],
  ['orders', 'Customer Orders'],
  ['customers', 'Customers'],
  ['order_payments', 'Order Payments'],
  ['tasks', 'Tasks'],
  ['users', 'User Management'],
  ['branches', 'Branch Management'],
] as const
const ACTIONS = [
  ['INSERT', 'Created'],
  ['UPDATE', 'Updated'],
  ['DELETE', 'Deleted'],
] as const

const SOURCES = [
  ['all', 'All Activity'],
  ['user', 'User Activity'],
  ['system', 'System Activity'],
] as const
type SourceKey = (typeof SOURCES)[number][0]

const PAGE_SIZE = 25

/** Owner-only view over the existing audit trail (read only: nothing here can change an audit row). */
export function ActivityHistoryPage() {
  const today = dubaiToday()
  const [filter, setFilter] = useState<FilterState>(() => {
    const r = rangeFor('last7', today)
    return { range: 'last7', from: r.from, to: r.to, period: 'day', branch: 'all' }
  })
  const [module, setModule] = useState('all')
  const [action, setAction] = useState('all')
  const [actor, setActor] = useState('all')
  const [source, setSource] = useState<SourceKey>('all')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const actors = useActors()

  const filters: ReportFilters = {
    date_from: filter.from,
    date_to: filter.to,
    period: 'day',
    ...(module !== 'all' ? { module } : {}),
    ...(action !== 'all' ? { action } : {}),
    ...(source !== 'all' ? { source } : {}),
    ...(actor !== 'all' && source !== 'system' ? { actor_id: actor } : {}),
    ...(q.trim() ? { q: q.trim() } : {}),
  }
  const report = useReport('activity', { ...filters, page, page_size: PAGE_SIZE })
  const reset = (p: () => void) => {
    p()
    setPage(1)
  }
  const onRange = (r: RangeKey) => {
    if (r === 'custom') return setFilter((f) => ({ ...f, range: 'custom' }))
    const { from, to } = rangeFor(r, today)
    reset(() => setFilter((f) => ({ ...f, range: r, from, to })))
  }

  return (
    <PageContainer
      title="Activity History"
      description="Who changed what, and when. System / Initial Setup entries are one-time setup events made with no signed-in user (the 10 branches and the first Owner profile). Passwords, tokens and keys are never shown. Owner only."
    >
      <ReportFilterBar
        value={filter}
        onRange={onRange}
        onChange={(p) => reset(() => setFilter((f) => ({ ...f, ...p })))}
        showPeriod={false}
        showBranch={false}
      />
      <div
        className="inline-flex w-fit rounded-md border p-0.5"
        role="group"
        aria-label="Activity source"
      >
        {SOURCES.map(([value, label]) => (
          <Button
            key={value}
            size="sm"
            variant={source === value ? 'default' : 'ghost'}
            aria-pressed={source === value}
            onClick={() => reset(() => setSource(value))}
          >
            {label}
          </Button>
        ))}
      </div>
      <div className="grid gap-3 rounded-xl border bg-card p-4 shadow-card sm:grid-cols-2 lg:grid-cols-4">
        <FormSelect
          label="User"
          disabled={source === 'system'}
          value={actor}
          options={[
            { value: 'all', label: 'All users' },
            ...(actors.data ?? []).map((a) => ({ value: a.id, label: a.name })),
          ]}
          onValueChange={(v) => reset(() => setActor(v))}
        />
        <FormSelect
          label="Module"
          value={module}
          options={[
            { value: 'all', label: 'All modules' },
            ...MODULES.map(([value, label]) => ({ value, label })),
          ]}
          onValueChange={(v) => reset(() => setModule(v))}
        />
        <FormSelect
          label="Action"
          value={action}
          options={[
            { value: 'all', label: 'All actions' },
            ...ACTIONS.map(([value, label]) => ({ value, label })),
          ]}
          onValueChange={(v) => reset(() => setAction(v))}
        />
        <FormInput
          label="Record reference"
          placeholder="Record id or reason"
          value={q}
          onChange={(e) => reset(() => setQ(e.target.value))}
        />
      </div>
      <SectionCard
        title="Changes"
        actions={<ExportButtons reportKey="activity" filters={filters} />}
      >
        <ReportTable
          report={report.data}
          isLoading={report.isLoading}
          error={report.error}
          onRetry={() => void report.refetch()}
          sort={undefined}
          desc={false}
          onSort={() => undefined}
          page={page}
          onPage={setPage}
        />
        {report.data?.notes.length ? (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
            {report.data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : null}
      </SectionCard>
    </PageContainer>
  )
}
