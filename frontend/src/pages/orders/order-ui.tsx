import { DataTable } from '@/components/common/data-table'
import { StatusBadge, type Status } from '@/components/common/status-badge'
import type { OrderRow } from '@/schemas/orders'
import { orderColumns } from './order-columns'

const ORDER_TONE: Record<string, Status> = {
  New: 'neutral',
  Scheduled: 'info',
  'Picked Up': 'info',
  Processing: 'warning',
  Ready: 'success',
  'Out for Delivery': 'warning',
  Delivered: 'success',
  Cancelled: 'danger',
}
const PAYMENT_TONE: Record<string, Status> = {
  Unpaid: 'danger',
  Partial: 'warning',
  Paid: 'success',
  Refunded: 'neutral',
}

export const OrderStatusBadge = ({ status }: { status: string }) => (
  <StatusBadge status={ORDER_TONE[status] ?? 'neutral'}>{status}</StatusBadge>
)
export const PaymentStatusBadge = ({ status }: { status: string }) => (
  <StatusBadge status={PAYMENT_TONE[status] ?? 'neutral'}>{status}</StatusBadge>
)

export function OrderTable({
  rows,
  caption,
  isLoading,
  error,
  onRetry,
  showBranch,
  emptyTitle = 'No orders to show',
  emptyDescription,
}: {
  rows: OrderRow[] | undefined
  caption: string
  isLoading?: boolean
  error?: unknown
  onRetry?: () => void
  showBranch: boolean
  emptyTitle?: string
  emptyDescription?: string
}) {
  return (
    <DataTable
      columns={orderColumns({ showBranch })}
      rows={rows}
      getRowId={(o) => o.id}
      caption={caption}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      emptyTitle={emptyTitle}
      emptyDescription={emptyDescription}
    />
  )
}
