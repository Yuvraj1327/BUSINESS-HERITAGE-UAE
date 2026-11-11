import { Ban, CircleDollarSign, Pencil, StepForward } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { DataTable } from '@/components/common/data-table'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { ReasonDialog } from '@/components/common/reason-dialog'
import { SectionCard } from '@/components/common/section-card'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useCancelOrder, useOrder, useSetStatus } from '@/hooks/use-orders'
import { getErrorMessage } from '@/lib/errors'
import { formatDate, formatDateTime } from '@/utils/format'
import { aed } from './order-format'
import { OrderStatusBadge, PaymentStatusBadge } from './order-ui'
import { PaymentDialog } from './PaymentDialog'

const Item = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="grid gap-0.5">
    <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
    <dd className="text-sm">{children || '—'}</dd>
  </div>
)

export function OrderDetailPage() {
  const { id = '' } = useParams()
  const q = useOrder(id)
  const setStatus = useSetStatus(id)
  const cancel = useCancelOrder(id)
  const [advance, setAdvance] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [paying, setPaying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const d = q.data

  if (q.isLoading)
    return (
      <PageContainer title="Order">
        <LoadingState rows={6} />
      </PageContainer>
    )
  if (q.isError || !d)
    return (
      <PageContainer title="Order">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </PageContainer>
    )
  const o = d.order

  async function moveOn() {
    if (!d?.next_status) return
    setError(null)
    try {
      await setStatus.mutateAsync({ status: d.next_status })
      toast.success(`Order marked ${d.next_status}`)
      setAdvance(false)
    } catch (e) {
      setError(getErrorMessage(e))
      setAdvance(false)
    }
  }

  return (
    <PageContainer
      title={`Order ${o.order_no}`}
      description={`${o.customer_name} · ${o.branch_name}`}
      actions={
        <div className="flex flex-wrap gap-2">
          {d.next_status ? (
            <Can module="orders" action="update">
              <Button onClick={() => setAdvance(true)}>
                <StepForward aria-hidden /> Mark {d.next_status}
              </Button>
            </Can>
          ) : null}
          {d.can_pay ? (
            <Can module="order_payments" action="create">
              <Button variant="outline" onClick={() => setPaying(true)}>
                <CircleDollarSign aria-hidden /> Record payment
              </Button>
            </Can>
          ) : null}
          {d.can_edit ? (
            <Can module="orders" action="update">
              <Button variant="outline" asChild>
                <Link to={`/orders/${id}/edit`}>
                  <Pencil aria-hidden /> Edit
                </Link>
              </Button>
            </Can>
          ) : null}
          {d.can_cancel ? (
            <Can module="orders" action="manage">
              <Button variant="destructive" onClick={() => setCancelling(true)}>
                <Ban aria-hidden /> Cancel order
              </Button>
            </Can>
          ) : null}
        </div>
      }
    >
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <OrderStatusBadge status={o.status} />
        <PaymentStatusBadge status={o.payment_status} />
        {o.overdue ? (
          <span className="text-sm font-medium text-destructive">
            {o.overdue === 'pickup' ? 'Pickup overdue' : 'Delivery overdue'}
          </span>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <SectionCard title="Order" className="lg:col-span-2">
          <dl className="grid gap-4 sm:grid-cols-2">
            <Item label="Order date">{formatDate(o.order_date)}</Item>
            <Item label="Service">{`${o.category} · ${o.service_type}`}</Item>
            <Item label="Pickup">{formatDateTime(o.pickup_at)}</Item>
            <Item label="Pickup address">{o.pickup_address}</Item>
            <Item label="Expected delivery">{formatDateTime(o.delivery_at)}</Item>
            <Item label="Delivery address">{o.delivery_address}</Item>
            <Item label="Notes">{d.notes}</Item>
            <Item label="Created">{`${formatDateTime(d.created_at)}${d.created_by_name ? ` by ${d.created_by_name}` : ''}`}</Item>
            <Item label="Last updated">{`${formatDateTime(d.updated_at)}${d.updated_by_name ? ` by ${d.updated_by_name}` : ''}`}</Item>
            {d.cancel_reason ? <Item label="Cancellation reason">{d.cancel_reason}</Item> : null}
          </dl>
        </SectionCard>

        <SectionCard title="Customer">
          <dl className="grid gap-4">
            <Item label="Name">
              <Link to={`/customers/${o.customer_id}`} className="text-primary hover:underline">
                {o.customer_name}
              </Link>
            </Item>
            <Item label="Mobile">{o.mobile}</Item>
            <Item label="WhatsApp">{d.customer_whatsapp}</Item>
            <Item label="Area">{o.area}</Item>
            <Item label="Address">{d.customer_address}</Item>
          </dl>
        </SectionCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Payment summary">
          <dl className="grid gap-3 text-sm">
            {[
              ['Order total', aed(d.order_total)],
              ['Discount', `− ${aed(d.discount)}`],
              ['Service fee', `+ ${aed(d.service_fee)}`],
              ['Final payable', aed(o.final_payable)],
              ['Amount collected', aed(o.amount_collected)],
              ['Outstanding', aed(o.outstanding)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-b pb-2 last:border-0">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="tabular font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </SectionCard>

        <SectionCard
          title="Status timeline"
          description="Every change with who made it and when (Dubai time)."
        >
          <ol className="space-y-3" aria-label="Status timeline">
            {d.history.map((h) => (
              <li key={h.id} className="grid gap-0.5 border-l-2 border-teal pl-3">
                <span className="text-sm font-medium">
                  {h.from_status ? `${h.from_status} → ${h.to_status}` : h.to_status}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(h.changed_at)}
                  {h.changed_by ? ` · ${h.changed_by}` : ''}
                </span>
                {h.note ? <span className="text-xs">{h.note}</span> : null}
              </li>
            ))}
          </ol>
        </SectionCard>
      </div>

      <Can module="order_payments" action="read">
        <SectionCard
          title="Payment history"
          description="Payments are never deleted. Refunds need an approved workflow that is not set up yet."
        >
          <DataTable
            caption="Payment history"
            rows={d.payments}
            getRowId={(p) => p.id}
            emptyTitle="No payments yet"
            columns={[
              { key: 'date', header: 'Date', cell: (p) => formatDate(p.payment_date) },
              { key: 'amount', header: 'Amount', align: 'right', cell: (p) => aed(p.amount) },
              { key: 'method', header: 'Method', cell: (p) => p.method },
              { key: 'ref', header: 'Reference', cell: (p) => p.reference ?? '—' },
              { key: 'by', header: 'Recorded by', cell: (p) => p.recorded_by ?? '—' },
              { key: 'note', header: 'Note', cell: (p) => p.note ?? '—' },
            ]}
          />
        </SectionCard>
      </Can>

      <ConfirmDialog
        open={advance}
        onOpenChange={setAdvance}
        title={`Mark order ${d.next_status ?? ''}?`}
        description={`${o.order_no} moves from ${o.status} to ${d.next_status ?? ''}. This is recorded in the history.`}
        confirmLabel={`Mark ${d.next_status ?? ''}`}
        isLoading={setStatus.isPending}
        onConfirm={moveOn}
      />
      <ReasonDialog
        open={cancelling}
        onOpenChange={setCancelling}
        title="Cancel this order?"
        description="The order and its payments are kept for the record. A cancelled order cannot be reopened."
        confirmLabel="Cancel order"
        isLoading={cancel.isPending}
        onSubmit={async (reason) => {
          await cancel.mutateAsync(reason)
          toast.success('Order cancelled')
        }}
      />
      <PaymentDialog
        orderId={id}
        open={paying}
        onOpenChange={setPaying}
        outstanding={o.outstanding}
      />
    </PageContainer>
  )
}
