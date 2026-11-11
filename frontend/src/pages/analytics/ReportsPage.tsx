import {
  Banknote,
  BarChart3,
  Coins,
  HandCoins,
  PiggyBank,
  Receipt,
  ShoppingBag,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormSelect } from '@/components/forms/form-select'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useCatalog, useOverview, useReport } from '@/hooks/use-analytics'
import type { ReportFilters } from '@/services/analytics.service'
import { formatAED, dubaiToday } from '@/utils/format'
import { ChartsSection } from './ChartsSection'
import { ReportFilterBar, type FilterState } from './ReportFilterBar'
import { summaryText } from './cell-format'
import { ExportButtons, ReportTable } from './ReportTable'
import { rangeFor, type RangeKey } from './ranges'

const PAGE_SIZE = 25

export function ReportsPage() {
  const today = dubaiToday()
  const [filter, setFilter] = useState<FilterState>(() => ({
    range: 'this_month',
    ...(() => {
      const r = rangeFor('this_month', today)
      return { from: r.from, to: r.to }
    })(),
    period: 'day',
    branch: 'all',
  }))
  const [view, setView] = useState<'reports' | 'charts'>('reports')
  const [category, setCategory] = useState<string>('')
  const [key, setKey] = useState<string>('')
  const [sort, setSort] = useState<string | undefined>()
  const [desc, setDesc] = useState(false)
  const [page, setPage] = useState(1)

  const catalog = useCatalog()
  const items = useMemo(
    () => (catalog.data ?? []).filter((c) => c.category !== 'Activity'),
    [catalog.data],
  )
  const categories = useMemo(() => [...new Set(items.map((i) => i.category))], [items])
  const activeCategory = category || categories[0] || ''
  const inCategory = items.filter((i) => i.category === activeCategory)
  const activeKey = inCategory.some((i) => i.key === key) ? key : (inCategory[0]?.key ?? '')

  const filters: ReportFilters = {
    date_from: filter.from,
    date_to: filter.to,
    period: filter.period,
    ...(filter.branch !== 'all' ? { branch_id: filter.branch } : {}),
  }
  const valid = Boolean(filter.from && filter.to && filter.from <= filter.to)
  const overview = useOverview(filters)
  const report = useReport(activeKey, { ...filters, page, page_size: PAGE_SIZE, sort, desc })
  const k = overview.data?.kpis
  const money = (v: string | number | null | undefined) =>
    v === null || v === undefined ? undefined : formatAED(String(v))
  const cur = items.find((i) => i.key === activeKey)

  const onRange = (r: RangeKey) => {
    if (r === 'custom') return setFilter((f) => ({ ...f, range: 'custom' }))
    const { from, to } = rangeFor(r, today)
    setFilter((f) => ({ ...f, range: r, from, to }))
    setPage(1)
  }
  const onChange = (p: Partial<FilterState>) => {
    setFilter((f) => ({ ...f, ...p }))
    setPage(1)
  }

  return (
    <PageContainer
      title="Reports & Analytics"
      description="Live figures from the same records and rules as the rest of the system. Owner only."
    >
      <ReportFilterBar value={filter} onRange={onRange} onChange={onChange} />
      {!valid ? (
        <p role="alert" className="text-sm text-destructive">
          Choose a start date that is on or before the end date.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Key figures">
        <StatCard
          label="Total Sales"
          icon={TrendingUp}
          isLoading={overview.isLoading}
          value={money(k?.total_sales)}
        />
        <StatCard
          label="Total Collections"
          icon={Coins}
          isLoading={overview.isLoading}
          value={money(k?.total_collections)}
        />
        <StatCard
          label="Total Orders"
          icon={ShoppingBag}
          isLoading={overview.isLoading}
          value={k ? String(k.total_orders) : undefined}
        />
        <StatCard
          label="Total Shop Expenses"
          icon={Receipt}
          isLoading={overview.isLoading}
          value={money(k?.shop_expenses)}
        />
        <StatCard
          label="Total Head Office Expenses"
          icon={Banknote}
          isLoading={overview.isLoading}
          value={money(k?.head_office_expenses)}
        />
        <StatCard
          label="Total Savings"
          icon={PiggyBank}
          isLoading={overview.isLoading}
          value={money(k?.total_savings)}
        />
        <StatCard
          label="Sales Minus Expenses"
          icon={HandCoins}
          isLoading={overview.isLoading}
          value={money(k?.sales_minus_expenses)}
        />
        <StatCard
          label="Cash + Bank Balance"
          icon={Wallet}
          isLoading={overview.isLoading}
          value={k ? (money(k.cash_bank_balance) ?? 'Not configured') : undefined}
          description={k?.balance_date ? `At ${k.balance_date}` : undefined}
        />
      </div>
      {overview.data?.notes.length ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          {overview.data.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}

      <div className="flex gap-2" role="tablist" aria-label="Reports or charts">
        <Button
          role="tab"
          aria-selected={view === 'reports'}
          variant={view === 'reports' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setView('reports')}
        >
          Reports
        </Button>
        <Button
          role="tab"
          aria-selected={view === 'charts'}
          variant={view === 'charts' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setView('charts')}
        >
          <BarChart3 aria-hidden /> Charts
        </Button>
      </div>

      {view === 'charts' ? (
        valid ? (
          <ChartsSection filters={filters} />
        ) : null
      ) : (
        <SectionCard
          title={cur?.title ?? 'Reports'}
          description={report.data?.description ?? cur?.description}
          actions={
            activeKey ? (
              <ExportButtons
                reportKey={activeKey}
                filters={{ ...filters, ...(sort ? { sort, desc } : {}) }}
              />
            ) : null
          }
        >
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2" role="tablist" aria-label="Report categories">
              {categories.map((c) => (
                <Button
                  key={c}
                  role="tab"
                  aria-selected={c === activeCategory}
                  size="sm"
                  variant={c === activeCategory ? 'default' : 'outline'}
                  onClick={() => {
                    setCategory(c)
                    setKey('')
                    setSort(undefined)
                    setPage(1)
                  }}
                >
                  {c}
                </Button>
              ))}
            </div>
            {inCategory.length > 1 ? (
              <FormSelect
                label="Report"
                value={activeKey}
                options={inCategory.map((i) => ({ value: i.key, label: i.title }))}
                onValueChange={(v) => {
                  setKey(v)
                  setSort(undefined)
                  setPage(1)
                }}
              />
            ) : null}
            {report.data?.summary.length ? (
              <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Report totals">
                {report.data.summary.map((s) => (
                  <div key={s.label} className="rounded-lg border bg-muted/40 p-3">
                    <dt className="text-xs text-muted-foreground">{s.label}</dt>
                    <dd className="text-base font-semibold tabular-nums">
                      {summaryText(s.kind, s.value)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : null}
            <ReportTable
              report={report.data}
              isLoading={report.isLoading}
              error={report.error}
              onRetry={() => void report.refetch()}
              sort={sort}
              desc={desc}
              onSort={(c) => {
                setDesc(sort === c ? !desc : false)
                setSort(c)
                setPage(1)
              }}
              page={page}
              onPage={setPage}
            />
            {report.data?.notes.length ? (
              <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                {report.data.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            ) : null}
          </div>
        </SectionCard>
      )}
    </PageContainer>
  )
}
