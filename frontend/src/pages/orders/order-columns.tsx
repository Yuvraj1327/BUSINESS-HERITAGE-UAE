import { Link } from 'react-router-dom'
import type { DataTableColumn } from '@/components/common/data-table'
import type { OrderRow } from '@/schemas/orders'
import { formatDateTime } from '@/utils/format'
import { aed } from './order-format'
import { OrderStatusBadge, PaymentStatusBadge } from './order-ui'

/** Same wording everywhere an order is listed, so the dashboard, search and operations screens agree. */
export function orderColumns(opts: { showBranch: boolean }): DataTableColumn<OrderRow>[] {
  const cols: DataTableColumn<OrderRow>[] = [
    {
      key: 'order_no',
      header: 'Order',
      cell: (o) => (
        <div className="grid">
          <Link
            to={`/orders/${o.id}`}
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            {o.order_no}
          </Link>
          {o.overdue ? (
            <span className="text-xs font-medium text-destructive">
              {o.overdue === 'pickup' ? 'Pickup overdue' : 'Delivery overdue'}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'customer',
      header: 'Customer',
      cell: (o) => (
        <div className="grid">
          <span>{o.customer_name}</span>
          <span className="text-xs text-muted-foreground">
            {o.mobile}
            {o.area ? ` · ${o.area}` : ''}
          </span>
        </div>
      ),
    },
  ]
  if (opts.showBranch) cols.push({ key: 'branch', header: 'Branch', cell: (o) => o.branch_name })
  cols.push(
    {
      key: 'service',
      header: 'Service',
      cell: (o) => `${o.category} · ${o.service_type}`,
    },
    { key: 'pickup', header: 'Pickup', cell: (o) => formatDateTime(o.pickup_at) },
    { key: 'delivery', header: 'Delivery', cell: (o) => formatDateTime(o.delivery_at) },
    { key: 'status', header: 'Status', cell: (o) => <OrderStatusBadge status={o.status} /> },
    {
      key: 'payment',
      header: 'Payment',
      cell: (o) => <PaymentStatusBadge status={o.payment_status} />,
    },
    { key: 'total', header: 'Total', align: 'right', cell: (o) => aed(o.final_payable) },
    { key: 'outstanding', header: 'Outstanding', align: 'right', cell: (o) => aed(o.outstanding) },
  )
  return cols
}
