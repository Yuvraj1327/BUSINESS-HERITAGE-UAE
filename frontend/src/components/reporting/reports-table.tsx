import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { StatusBadge } from '@/components/common/status-badge'
import type { DailyReport } from '@/schemas/reports'
import { formatAED, formatDate } from '@/utils/format'

/** Difference = Total Sales − Total Collections, computed by the API. Matches/Diff is the server's verdict. */
function reportColumns(
  extra?: (r: DailyReport) => React.ReactNode,
): DataTableColumn<DailyReport>[] {
  const cols: DataTableColumn<DailyReport>[] = [
    {
      key: 'date',
      header: 'Date',
      cell: (r) => formatDate(r.report_date),
      className: 'whitespace-nowrap',
    },
    { key: 'branch', header: 'Branch', cell: (r) => r.branch_name, className: 'whitespace-nowrap' },
    { key: 'sales', header: 'Total Sales', align: 'right', cell: (r) => formatAED(r.total_sales) },
    { key: 'orders', header: 'Orders', align: 'right', cell: (r) => r.order_count },
    { key: 'cash', header: 'Cash', align: 'right', cell: (r) => formatAED(r.cash_received) },
    { key: 'pos', header: 'POS', align: 'right', cell: (r) => formatAED(r.pos_amount) },
    {
      key: 'bank',
      header: 'Bank Transfers',
      align: 'right',
      cell: (r) => formatAED(r.bank_transfer),
    },
    {
      key: 'links',
      header: 'Payment Links',
      align: 'right',
      cell: (r) => formatAED(r.link_payment),
    },
    {
      key: 'collections',
      header: 'Total Collections',
      align: 'right',
      cell: (r) => formatAED(r.total_received),
    },
    {
      key: 'expenses',
      header: 'Shop Expenses',
      align: 'right',
      cell: (r) => formatAED(r.shop_expenses),
    },
    { key: 'savings', header: 'Savings', align: 'right', cell: (r) => formatAED(r.shop_savings) },
    {
      key: 'difference',
      header: 'Difference',
      align: 'right',
      cell: (r) => (
        <span className="inline-flex items-center justify-end gap-2">
          {formatAED(r.difference)}
          <StatusBadge status={r.check === 'Matches' ? 'success' : 'warning'}>
            {r.check}
          </StatusBadge>
        </span>
      ),
    },
  ]
  if (extra) cols.push({ key: 'actions', header: 'Actions', cell: extra })
  return cols
}

interface ReportsTableProps {
  rows: DailyReport[] | undefined
  isLoading?: boolean
  error?: unknown
  onRetry?: () => void
  caption: string
  emptyTitle?: string
  emptyDescription?: string
  extra?: (r: DailyReport) => React.ReactNode
}

export function ReportsTable({ rows, extra, ...rest }: ReportsTableProps) {
  return (
    <DataTable
      columns={reportColumns(extra)}
      rows={rows}
      getRowId={(r) => r.id}
      emptyTitle="No reports found"
      emptyDescription="No daily reports match these filters."
      {...rest}
    />
  )
}
