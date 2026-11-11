import { Download, FileSpreadsheet } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { SectionCard } from '@/components/common/section-card'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useOrderExport, useOrderReport, useOrderReportCatalog } from '@/hooks/use-orders'
import type { Report, ReportRow } from '@/schemas/analytics'
import type { OrderReportFilters } from '@/services/orders.service'
import { ReportFilterBar, type FilterState } from '@/pages/analytics/ReportFilterBar'
import { cellText, summaryText } from '@/pages/analytics/cell-format'
import { rangeFor, type RangeKey } from '@/pages/analytics/ranges'
import { dubaiToday } from '@/utils/format'

const PAGE_SIZE = 25

/** Operational reports for customer orders. Uses the same table, filter and export conventions as Step 12 reports. */
export function OrderReportsPage() {
  const today = dubaiToday()
  const { canChoose, selectedBranchId } = useBranchContext()
  const [filter, setFilter] = useState<FilterState>(() => ({
    range: 'this_month',
    ...(() => {
      const r = rangeFor('this_month', today)
      return { from: r.from, to: r.to }
    })(),
    period: 'day',
    branch: 'all',
  }))
  const [key, setKey] = useState('')
  const [sort, setSort] = useState<string | undefined>()
  const [desc, setDesc] = useState(false)
  const [page, setPage] = useState(1)
  const cat = useOrderReportCatalog()
  const items = cat.data ?? []
  const active = items.some((i) => i.key === key) ? key : (items[0]?.key ?? '')
  const branch = canChoose ? (filter.branch !== 'all' ? filter.branch : selectedBranchId) : 'all'
  const filters: OrderReportFilters = {
    date_from: filter.from,
    date_to: filter.to,
    period: filter.period === 'week' ? 'week' : 'day',
    ...(branch !== 'all' ? { branch_id: branch } : {}),
    ...(sort ? { sort, desc } : {}),
  }
  const valid = Boolean(filter.from && filter.to && filter.from <= filter.to)
  const report = useOrderReport(active, { ...filters, page, page_size: PAGE_SIZE })
  const exp = useOrderExport()
  const cur = items.find((i) => i.key === active)

  const onRange = (r: RangeKey) => {
    if (r === 'custom') return setFilter((f) => ({ ...f, range: 'custom' }))
    const { from, to } = rangeFor(r, today)
    setFilter((f) => ({ ...f, range: r, from, to }))
    setPage(1)
  }
  const run = (format: 'csv' | 'xlsx') =>
    exp.mutate(
      { key: active, format, filters },
      {
        onSuccess: (n) => toast.success(`Downloaded ${n}`),
        onError: () => toast.error('The export could not be created. Please try again.'),
      },
    )
  const data: Report | undefined = report.data
  const columns: DataTableColumn<ReportRow>[] = (data?.columns ?? []).map((c) => ({
    key: c.key,
    header: c.label,
    align: c.kind === 'money' || c.kind === 'int' || c.kind === 'pct' ? 'right' : 'left',
    cell: (r) => cellText(c, r[c.key]),
  }))

  return (
    <PageContainer
      title="Order Reports"
      description="Counts, revenue, collections and outstanding for customer orders. These figures are separate from Daily Reports sales."
    >
      <ReportFilterBar
        value={filter}
        onRange={onRange}
        onChange={(p) => {
          setFilter((f) => ({ ...f, ...p }))
          setPage(1)
        }}
        showBranch={canChoose}
      />
      {!valid ? (
        <p role="alert" className="text-sm text-destructive">
          Choose a start date that is on or before the end date.
        </p>
      ) : null}
      <SectionCard
        title={cur?.title ?? 'Report'}
        description={data?.description ?? cur?.description}
        actions={
          active ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={exp.isPending || !valid}
                onClick={() => run('csv')}
              >
                <Download aria-hidden /> Export CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={exp.isPending || !valid}
                onClick={() => run('xlsx')}
              >
                <FileSpreadsheet aria-hidden /> Export Excel
              </Button>
            </div>
          ) : null
        }
      >
        <div className="space-y-4">
          <FormSelect
            label="Report"
            value={active}
            options={items.map((i) => ({ value: i.key, label: i.title }))}
            onValueChange={(v) => {
              setKey(v)
              setSort(undefined)
              setPage(1)
            }}
          />
          {data?.summary.length ? (
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Summary">
              {data.summary.map((s) => (
                <div key={s.label} className="rounded-lg border p-3">
                  <dt className="text-xs text-muted-foreground">{s.label}</dt>
                  <dd className="tabular text-lg font-semibold">{summaryText(s.kind, s.value)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {data ? (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Sort by">
              {data.columns.map((c) => (
                <Button
                  key={c.key}
                  size="sm"
                  variant={sort === c.key ? 'secondary' : 'ghost'}
                  aria-label={`Sort by ${c.label}`}
                  onClick={() => {
                    if (sort === c.key) setDesc((d) => !d)
                    else {
                      setSort(c.key)
                      setDesc(false)
                    }
                    setPage(1)
                  }}
                >
                  {c.label}
                </Button>
              ))}
            </div>
          ) : null}
          <DataTable
            columns={columns}
            rows={valid ? data?.rows : []}
            getRowId={(r) => JSON.stringify(r)}
            caption={data?.title ?? 'Order report'}
            isLoading={report.isLoading || cat.isLoading}
            error={report.error ?? cat.error}
            onRetry={() => void report.refetch()}
            emptyTitle="No orders for these filters"
            emptyDescription="Try a wider date range or another branch."
          />
          {data ? (
            <Pagination
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              noun="rows"
              onPage={setPage}
            />
          ) : null}
          {data?.notes.length ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              {data.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </SectionCard>
    </PageContainer>
  )
}
