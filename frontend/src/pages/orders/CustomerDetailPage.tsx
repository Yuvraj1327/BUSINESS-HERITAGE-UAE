import { Pencil, PackagePlus } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { Pagination } from '@/components/common/pagination'
import { SectionCard } from '@/components/common/section-card'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useCustomer, useCustomerOrders } from '@/hooks/use-orders'
import { formatDate } from '@/utils/format'
import { aed } from './order-format'
import { OrderTable } from './order-ui'
import { CustomerDialog } from './CustomerDialog'

export function CustomerDetailPage() {
  const { id = '' } = useParams()
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState(false)
  const c = useCustomer(id)
  const orders = useCustomerOrders(id, page)
  if (c.isLoading)
    return (
      <PageContainer title="Customer">
        <LoadingState rows={5} />
      </PageContainer>
    )
  if (c.isError || !c.data)
    return (
      <PageContainer title="Customer">
        <ErrorState error={c.error} onRetry={() => void c.refetch()} />
      </PageContainer>
    )
  const d = c.data
  const rows: [string, string][] = [
    ['Mobile', d.mobile],
    ['WhatsApp', d.whatsapp ?? '—'],
    ['Area', d.area ?? '—'],
    ['Address', d.address ?? '—'],
    ['Branch', d.branch_name],
    ['Notes', d.notes ?? '—'],
    ['Orders', String(d.order_count)],
    ['Total billed', aed(d.total_billed)],
    ['Outstanding', aed(d.outstanding)],
    ['Last order', d.last_order_date ? formatDate(d.last_order_date) : '—'],
  ]
  return (
    <PageContainer
      title={d.name}
      description={`Customer of ${d.branch_name}`}
      actions={
        <div className="flex gap-2">
          <Can module="orders" action="create">
            <Button variant="outline" asChild>
              <Link to="/orders/new">
                <PackagePlus aria-hidden /> New order
              </Link>
            </Button>
          </Can>
          <Can module="customers" action="update">
            <Button onClick={() => setEditing(true)}>
              <Pencil aria-hidden /> Edit
            </Button>
          </Can>
        </div>
      }
    >
      <SectionCard title="Details">
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map(([k, v]) => (
            <div key={k} className="grid gap-0.5">
              <dt className="text-xs font-medium text-muted-foreground">{k}</dt>
              <dd className="text-sm">{v}</dd>
            </div>
          ))}
        </dl>
      </SectionCard>
      <SectionCard title="Order history">
        <div className="space-y-3">
          <OrderTable
            rows={orders.data?.items}
            caption="Order history"
            isLoading={orders.isLoading}
            error={orders.error}
            onRetry={() => void orders.refetch()}
            showBranch={false}
            emptyTitle="No orders yet"
          />
          {orders.data ? (
            <Pagination
              page={orders.data.page}
              pageSize={orders.data.page_size}
              total={orders.data.total}
              noun="orders"
              onPage={setPage}
            />
          ) : null}
        </div>
      </SectionCard>
      <CustomerDialog open={editing} onOpenChange={setEditing} customer={d} />
    </PageContainer>
  )
}
