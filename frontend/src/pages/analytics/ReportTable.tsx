import { ArrowDown, ArrowUp, ArrowUpDown, Download, FileSpreadsheet } from 'lucide-react'
import { toast } from 'sonner'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { Button } from '@/components/ui/button'
import { useExport } from '@/hooks/use-analytics'
import type { Report, ReportRow } from '@/schemas/analytics'
import type { ReportFilters } from '@/services/analytics.service'
import { cellText } from './cell-format'

interface Props {
  report: Report | undefined
  isLoading: boolean
  error: unknown
  onRetry: () => void
  sort: string | undefined
  desc: boolean
  onSort: (key: string) => void
  page: number
  onPage: (p: number) => void
}

export function ReportTable({
  report,
  isLoading,
  error,
  onRetry,
  sort,
  desc,
  onSort,
  page,
  onPage,
}: Props) {
  const columns: DataTableColumn<ReportRow>[] = (report?.columns ?? []).map((c) => {
    const numeric = c.kind === 'money' || c.kind === 'int' || c.kind === 'pct'
    return {
      key: c.key,
      align: numeric ? 'right' : 'left',
      header: c.label,
      cell: (r) => cellText(c, r[c.key]),
    } satisfies DataTableColumn<ReportRow>
  })
  return (
    <div className="space-y-3">
      {report ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Sort by">
          {report.columns.map((c) => (
            <Button
              key={c.key}
              size="sm"
              variant={sort === c.key ? 'secondary' : 'ghost'}
              aria-label={`Sort by ${c.label}`}
              onClick={() => onSort(c.key)}
            >
              {c.label}
              {sort === c.key ? (
                desc ? (
                  <ArrowDown aria-hidden />
                ) : (
                  <ArrowUp aria-hidden />
                )
              ) : (
                <ArrowUpDown aria-hidden className="opacity-40" />
              )}
            </Button>
          ))}
        </div>
      ) : null}
      <DataTable
        columns={columns}
        rows={report?.rows}
        getRowId={(r) => JSON.stringify(r)}
        caption={report?.title ?? 'Report'}
        isLoading={isLoading}
        error={error}
        onRetry={onRetry}
        emptyTitle="No data for these filters"
        emptyDescription="Try a wider date range or another branch."
      />
      {report ? (
        <Pagination
          page={page}
          pageSize={report.page_size}
          total={report.total}
          noun="rows"
          onPage={onPage}
        />
      ) : null}
    </div>
  )
}

/** CSV / Excel buttons. The server builds the file from the same filters, so totals match the screen. */
export function ExportButtons({
  reportKey,
  filters,
}: {
  reportKey: string
  filters: ReportFilters & { sort?: string; desc?: boolean }
}) {
  const exp = useExport()
  const run = (format: 'csv' | 'xlsx') =>
    exp.mutate(
      { key: reportKey, format, filters },
      {
        onSuccess: (name) => toast.success(`Downloaded ${name}`),
        onError: () => toast.error('The export could not be created. Please try again.'),
      },
    )
  const busy = exp.isPending
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" disabled={busy} onClick={() => run('csv')}>
        <Download aria-hidden /> Export CSV
      </Button>
      <Button variant="outline" size="sm" disabled={busy} onClick={() => run('xlsx')}>
        <FileSpreadsheet aria-hidden /> Export Excel
      </Button>
      {busy ? (
        <span role="status" className="text-sm text-muted-foreground">
          Preparing your export…
        </span>
      ) : null}
      {exp.isError ? (
        <span role="alert" className="text-sm text-destructive">
          Export failed.
        </span>
      ) : null}
    </div>
  )
}
