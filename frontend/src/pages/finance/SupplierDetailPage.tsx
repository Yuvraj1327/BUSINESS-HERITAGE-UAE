import { ArrowLeft, Ban, CheckCircle2, CirclePlus, HandCoins, Pencil } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { Pagination } from '@/components/common/pagination'
import { ReasonDialog } from '@/components/common/reason-dialog'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { StatusBadge } from '@/components/common/status-badge'
import { FormSelect } from '@/components/forms/form-select'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import {
  useBalances,
  useSupplier,
  useSupplierEntries,
  useVoidSupplierEntry,
} from '@/hooks/use-finance'
import type { SupplierEntry } from '@/schemas/finance'
import { formatAED, formatDate } from '@/utils/format'
import { SupplierDialog } from './SupplierDialog'
import { DueDialog, MarkPaidDialog, PaymentDialog } from './SupplierPayments'

const PAGE_SIZE = 25

export function SupplierDetailPage() {
  const { id = '' } = useParams()
  const supplier = useSupplier(id)
  const balances = useBalances()
  const start = balances.data?.tracking_start ?? undefined
  const [kind, setKind] = useState('all')
  const [page, setPage] = useState(1)
  const entries = useSupplierEntries(id, {
    page,
    page_size: PAGE_SIZE,
    ...(kind !== 'all' ? { kind } : {}),
  })
  const voidEntry = useVoidSupplierEntry()

  const [editing, setEditing] = useState(false)
  const [paying, setPaying] = useState(false)
  const [due, setDue] = useState(false)
  const [markPaid, setMarkPaid] = useState(false)
  const [voiding, setVoiding] = useState<SupplierEntry | null>(null)

  if (supplier.isLoading) return <LoadingState label="Loading supplier…" />
  if (supplier.error || !supplier.data)
    return (
      <PageContainer title="Supplier">
        <ErrorState error={supplier.error} onRetry={() => void supplier.refetch()} />
      </PageContainer>
    )
  const s = supplier.data
  const owes = Number(s.outstanding) > 0
  const configured = balances.data?.status === 'ok'

  const columns: DataTableColumn<SupplierEntry>[] = [
    { key: 'd', header: 'Date', cell: (r) => formatDate(r.entry_date) },
    { key: 'k', header: 'Type', cell: (r) => (r.kind === 'payment' ? 'Payment' : 'New due') },
    { key: 'a', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
    { key: 'f', header: 'Paid from', cell: (r) => r.paid_from ?? '—' },
    {
      key: 'r',
      header: 'Reference / notes',
      cell: (r) => [r.reference, r.note].filter(Boolean).join(' · ') || '—',
      className: 'max-w-48 truncate',
    },
    { key: 'b', header: 'By', cell: (r) => r.created_by_name ?? '—' },
    {
      key: 'x',
      header: 'Status',
      cell: (r) =>
        r.voided ? (
          <StatusBadge status="neutral">Voided</StatusBadge>
        ) : (
          <Can module="suppliers" action="update">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setVoiding(r)}
              aria-label={`Void ${r.kind} ${r.entry_date}`}
            >
              <Ban aria-hidden /> Void
            </Button>
          </Can>
        ),
    },
  ]

  return (
    <PageContainer
      title={s.name}
      description={
        [s.category, s.payment_terms && `Terms: ${s.payment_terms}`].filter(Boolean).join(' · ') ||
        'Supplier details'
      }
      actions={
        <>
          <Button variant="outline" asChild>
            <Link to="/suppliers">
              <ArrowLeft aria-hidden /> All suppliers
            </Link>
          </Button>
          <Can module="suppliers" action="update">
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil aria-hidden /> Edit
            </Button>
          </Can>
        </>
      }
    >
      {!s.is_active ? <StatusBadge status="neutral">Inactive</StatusBadge> : null}
      {!configured && balances.data ? (
        <p
          role="status"
          className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
        >
          Opening balances are not configured yet, so dues and payments cannot be recorded.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Supplier balance">
        <StatCard
          label="Opening outstanding"
          value={formatAED(s.opening_outstanding)}
          description="Owed before tracking started"
        />
        <StatCard label="New dues" value={formatAED(s.new_dues)} />
        <StatCard label="Paid" value={formatAED(s.total_paid)} />
        <StatCard
          label="Outstanding"
          value={formatAED(s.outstanding)}
          description="Opening + new dues − payments"
        />
      </div>

      <Can module="suppliers" action="create">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setPaying(true)} disabled={!configured || !owes}>
            <HandCoins aria-hidden /> Record payment
          </Button>
          <Button
            variant="outline"
            onClick={() => setMarkPaid(true)}
            disabled={!configured || !owes}
          >
            <CheckCircle2 aria-hidden /> Mark as Paid
          </Button>
          <Button
            variant="outline"
            onClick={() => setDue(true)}
            disabled={!configured || !s.is_active}
          >
            <CirclePlus aria-hidden /> Add new due
          </Button>
        </div>
      </Can>

      {s.notes ? (
        <SectionCard title="Notes">
          <p className="text-sm whitespace-pre-wrap">{s.notes}</p>
        </SectionCard>
      ) : null}

      <SectionCard
        title="Dues and payment history"
        description="Newest first. Voided entries stay visible but no longer count."
      >
        <div className="space-y-4">
          <div className="max-w-xs">
            <FormSelect
              label="Show"
              value={kind}
              onValueChange={(v) => {
                setKind(v)
                setPage(1)
              }}
              options={[
                { value: 'all', label: 'Dues and payments' },
                { value: 'payment', label: 'Payments only' },
                { value: 'due', label: 'Dues only' },
              ]}
            />
          </div>
          <DataTable
            caption="Supplier dues and payments"
            rows={entries.data?.items}
            isLoading={entries.isLoading}
            error={entries.error}
            onRetry={() => void entries.refetch()}
            getRowId={(r) => r.id}
            columns={columns}
            emptyTitle="No dues or payments recorded"
          />
          {entries.data ? (
            <Pagination
              page={entries.data.page}
              pageSize={entries.data.page_size}
              total={entries.data.total}
              noun="entries"
              onPage={setPage}
            />
          ) : null}
        </div>
      </SectionCard>

      <SupplierDialog
        open={editing}
        onOpenChange={setEditing}
        supplier={s}
        openingEditable={false}
      />
      <PaymentDialog supplier={s} open={paying} onOpenChange={setPaying} minDate={start} />
      <DueDialog supplier={s} open={due} onOpenChange={setDue} minDate={start} />
      <MarkPaidDialog supplier={s} open={markPaid} onOpenChange={setMarkPaid} />
      <ReasonDialog
        open={voiding !== null}
        onOpenChange={(o) => !o && setVoiding(null)}
        title={`Void this ${voiding?.kind === 'payment' ? 'payment' : 'due'}?`}
        confirmLabel="Void entry"
        isLoading={voidEntry.isPending}
        description={
          voiding
            ? `${formatAED(voiding.amount)} on ${formatDate(voiding.entry_date)}. The outstanding amount is recalculated; the entry stays in the history.`
            : null
        }
        onSubmit={async (reason) => {
          await voidEntry.mutateAsync({ id: (voiding as SupplierEntry).id, reason })
          toast.success('Entry voided')
        }}
      />
    </PageContainer>
  )
}
