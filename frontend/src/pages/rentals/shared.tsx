import { Link } from 'react-router-dom'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { StatusBadge, type Status } from '@/components/common/status-badge'
import type { AuditEntry } from '@/schemas/finance'
import type { AgreementStatus, Cheque, ScheduleLine, SchedulePreview } from '@/schemas/rentals'
import { formatAED, formatDate } from '@/utils/format'
import { describeChange, dueText } from './helpers'

/* ---------- indicators: always colour + word (never colour alone) ---------- */
const AGREEMENT: Record<AgreementStatus, Status> = {
  Active: 'success',
  Scheduled: 'info',
  Expiring: 'warning',
  Expired: 'danger',
  Renewed: 'neutral',
  Terminated: 'neutral',
}
export const AgreementBadge = ({ status }: { status: AgreementStatus }) => (
  <StatusBadge status={AGREEMENT[status]}>{status}</StatusBadge>
)

export function ChequeBadge({ cheque }: { cheque: Cheque }) {
  if (cheque.status === 'Cleared') return <StatusBadge status="success">Cleared</StatusBadge>
  if (cheque.status === 'Bounced')
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <StatusBadge status="danger">Bounced</StatusBadge>
        {cheque.superseded ? (
          <span className="text-xs text-muted-foreground">Replaced by {cheque.replaced_by_no}</span>
        ) : (
          <span className="text-xs text-muted-foreground">Needs replacement</span>
        )}
      </span>
    )
  const tone: Status =
    cheque.timing === 'overdue' ? 'danger' : cheque.timing === 'later' ? 'neutral' : 'warning'
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <StatusBadge status={tone}>{cheque.timing === 'overdue' ? 'Overdue' : 'Pending'}</StatusBadge>
      {cheque.timing !== 'later' ? (
        <span className="text-xs text-muted-foreground">{dueText(cheque.days_to_due)}</span>
      ) : null}
    </span>
  )
}

/* ---------- schedule review (preview before confirming; the server generated every line) ---------- */
export function SchedulePreviewTable({
  preview,
  caption,
}: {
  preview: SchedulePreview
  caption: string
}) {
  const columns: DataTableColumn<ScheduleLine>[] = [
    { key: 'n', header: '#', cell: (r) => String(r.seq + 1) },
    { key: 'd', header: 'Cheque date', cell: (r) => formatDate(r.cheque_date) },
    { key: 'no', header: 'Cheque number', cell: (r) => r.cheque_no },
    { key: 'b', header: 'Bank', cell: (r) => r.bank },
    { key: 'a', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
    {
      key: 's',
      header: 'Status',
      cell: (r) => <StatusBadge status="neutral">{r.status}</StatusBadge>,
    },
  ]
  return (
    <div className="space-y-3">
      <DataTable
        caption={caption}
        rows={preview.lines}
        getRowId={(r) => String(r.seq)}
        columns={columns}
      />
      <dl className="grid gap-2 rounded-md border bg-muted/40 p-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Total annual rent</dt>
          <dd className="font-semibold">{formatAED(preview.annual_rent)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">
            Total cheque value ({preview.cheque_count} cheques)
          </dt>
          <dd className="font-semibold">{formatAED(preview.total_cheque_value)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Check</dt>
          <dd>
            {preview.matches ? (
              <StatusBadge status="success">Total equals the annual rent</StatusBadge>
            ) : (
              <StatusBadge status="danger">Total does not equal the rent</StatusBadge>
            )}
          </dd>
        </div>
      </dl>
    </div>
  )
}

/* ---------- cheque history ---------- */
export function ChequeHistory({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">No history yet.</p>
  return (
    <ol className="space-y-3" aria-label="Change history">
      {entries.map((e) => (
        <li key={e.id} className="rounded-md border p-3 text-sm">
          <p className="font-medium">{describeChange(e)}</p>
          <p className="text-xs text-muted-foreground">
            {new Intl.DateTimeFormat('en-GB', {
              dateStyle: 'medium',
              timeStyle: 'short',
              timeZone: 'Asia/Dubai',
            }).format(new Date(e.occurred_at))}{' '}
            · {e.actor_name ?? 'System'}
            {e.reason ? ` · Reason: ${e.reason}` : ''}
          </p>
        </li>
      ))}
    </ol>
  )
}

export function ChequeLink({ cheque }: { cheque: Cheque }) {
  return (
    <Link
      to={`/pdc-cheques/${cheque.id}`}
      className="font-medium text-primary underline-offset-4 hover:underline"
    >
      {cheque.cheque_no}
    </Link>
  )
}
