import { ArrowLeft, Pencil, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { StatusBadge } from '@/components/common/status-badge'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useAgreement } from '@/hooks/use-rentals'
import type { Cheque, RenewalLink } from '@/schemas/rentals'
import { formatAED, formatDate } from '@/utils/format'
import { AgreementDialog } from './AgreementDialog'
import { ChequeActions } from './ChequeActions'
import { endText } from './helpers'
import { AgreementBadge, ChequeBadge, ChequeHistory, ChequeLink } from './shared'
import { RenewDialog } from './RenewDialog'

const RELATION = {
  previous: 'Previous agreement',
  current: 'This agreement',
  next: 'Renewal',
} as const

export function AgreementDetailPage() {
  const { id = '' } = useParams()
  const detail = useAgreement(id)
  const [editing, setEditing] = useState(false)
  const [renewing, setRenewing] = useState(false)

  if (detail.isLoading) return <LoadingState label="Loading agreement…" />
  if (detail.error || !detail.data)
    return (
      <PageContainer title="Rental agreement">
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      </PageContainer>
    )
  const a = detail.data.agreement
  const sch = detail.data.schedule
  const open = a.stored_status === 'Active'
  const renewable = open && a.renewed_to_id === null

  const columns: DataTableColumn<Cheque>[] = [
    { key: 'd', header: 'Cheque date', cell: (r) => formatDate(r.cheque_date) },
    { key: 'n', header: 'Number', cell: (r) => <ChequeLink cheque={r} /> },
    { key: 'b', header: 'Bank', cell: (r) => r.bank },
    { key: 'a', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
    { key: 's', header: 'Status', cell: (r) => <ChequeBadge cheque={r} /> },
    {
      key: 'c',
      header: 'Cleared / bounced on',
      cell: (r) =>
        r.cleared_on ? formatDate(r.cleared_on) : r.bounced_on ? formatDate(r.bounced_on) : '—',
    },
    { key: 'x', header: 'Actions', cell: (r) => <ChequeActions cheque={r} compact /> },
  ]
  const renewalColumns: DataTableColumn<RenewalLink>[] = [
    {
      key: 'r',
      header: 'Agreement',
      cell: (r) =>
        r.relation === 'current' ? (
          RELATION.current
        ) : (
          <Link to={`/rentals/${r.id}`} className="font-medium text-primary hover:underline">
            {RELATION[r.relation]}
          </Link>
        ),
    },
    {
      key: 'p',
      header: 'Period',
      cell: (r) => `${formatDate(r.start_date)} – ${formatDate(r.end_date)}`,
    },
    { key: 'a', header: 'Annual rent', align: 'right', cell: (r) => formatAED(r.annual_rent) },
    {
      key: 'c',
      header: 'Cheques',
      cell: (r) => (r.cheque_count === null ? '—' : String(r.cheque_count)),
    },
    { key: 's', header: 'Status', cell: (r) => <AgreementBadge status={r.status} /> },
  ]

  return (
    <PageContainer
      title={`${a.branch_name} · ${a.landlord}`}
      description={a.unit ?? 'Rental agreement'}
      actions={
        <>
          <Button variant="outline" asChild>
            <Link to="/rentals">
              <ArrowLeft aria-hidden /> All agreements
            </Link>
          </Button>
          <Can module="rentals_cheques" action="update">
            <Button variant="outline" onClick={() => setEditing(true)} disabled={!open}>
              <Pencil aria-hidden /> Edit
            </Button>
          </Can>
          <Can module="rentals_cheques" action="create">
            <Button onClick={() => setRenewing(true)} disabled={!renewable}>
              <RefreshCw aria-hidden /> Renew
            </Button>
          </Can>
        </>
      }
    >
      {!open ? (
        <p className="text-sm text-muted-foreground">
          This agreement is {a.status.toLowerCase()}, so it can no longer be edited or renewed.
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Status"
          value={<AgreementBadge status={a.status} />}
          description={endText(a.days_to_end)}
        />
        <StatCard
          label="Period"
          value={`${formatDate(a.start_date)} – ${formatDate(a.end_date)}`}
        />
        <StatCard
          label="Annual rent"
          value={formatAED(a.annual_rent)}
          description={a.bank ? `Paid by PDC from ${a.bank}` : undefined}
        />
        <StatCard
          label="Cheques"
          value={`${sch.cleared} cleared · ${sch.pending} pending`}
          description={sch.bounced > 0 ? `${sch.bounced} bounced` : undefined}
        />
      </div>

      <SectionCard
        title="PDC cheque schedule"
        description="Cleared and bounced cheques are final records. A bounced cheque is replaced by a new linked cheque."
      >
        <div className="space-y-3">
          <DataTable
            caption="PDC cheque schedule"
            rows={sch.items}
            getRowId={(r) => r.id}
            columns={columns}
            emptyTitle="No cheques"
          />
          <dl className="grid gap-2 rounded-md border bg-muted/40 p-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Total rent</dt>
              <dd className="font-semibold">{formatAED(sch.annual_rent)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">
                Total cheque value ({sch.cheque_count} cheques)
              </dt>
              <dd className="font-semibold">{formatAED(sch.total_cheque_value)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Check</dt>
              <dd>
                {sch.matches ? (
                  <StatusBadge status="success">Total equals the annual rent</StatusBadge>
                ) : (
                  <StatusBadge status="danger">Total does not equal the rent</StatusBadge>
                )}
              </dd>
            </div>
          </dl>
        </div>
      </SectionCard>

      {a.notes ? (
        <SectionCard title="Notes">
          <p className="text-sm whitespace-pre-wrap">{a.notes}</p>
        </SectionCard>
      ) : null}

      {detail.data.renewals.length > 1 ? (
        <SectionCard
          title="Renewal history"
          description="The chain of agreements this one belongs to."
        >
          <DataTable
            caption="Renewal history"
            rows={detail.data.renewals}
            getRowId={(r) => r.id}
            columns={renewalColumns}
          />
        </SectionCard>
      ) : null}

      <SectionCard title="Change history" description="Every edit, who made it and why.">
        <ChequeHistory entries={detail.data.history} />
      </SectionCard>

      <AgreementDialog open={editing} onOpenChange={setEditing} agreement={a} />
      <RenewDialog open={renewing} onOpenChange={setRenewing} agreement={a} />
    </PageContainer>
  )
}
