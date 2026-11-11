import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useCheque } from '@/hooks/use-rentals'
import { formatAED, formatDate } from '@/utils/format'
import { ChequeActions } from './ChequeActions'
import { AgreementBadge, ChequeBadge, ChequeHistory } from './shared'

export function ChequeDetailPage() {
  const { id = '' } = useParams()
  const detail = useCheque(id)
  if (detail.isLoading) return <LoadingState label="Loading cheque…" />
  if (detail.error || !detail.data)
    return (
      <PageContainer title="PDC cheque">
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      </PageContainer>
    )
  const c = detail.data.cheque
  const a = detail.data.agreement
  return (
    <PageContainer
      title={`Cheque ${c.cheque_no}`}
      description={`${c.branch_name} · ${c.landlord}`}
      actions={
        <>
          <Button variant="outline" asChild>
            <Link to="/pdc-cheques">
              <ArrowLeft aria-hidden /> All cheques
            </Link>
          </Button>
          <ChequeActions cheque={c} />
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Status" value={<ChequeBadge cheque={c} />} />
        <StatCard label="Cheque date" value={formatDate(c.cheque_date)} />
        <StatCard label="Amount" value={formatAED(c.amount)} description={`Bank: ${c.bank}`} />
        <StatCard
          label={c.status === 'Bounced' ? 'Bounced on' : 'Cleared on'}
          value={
            c.cleared_on ? formatDate(c.cleared_on) : c.bounced_on ? formatDate(c.bounced_on) : '—'
          }
          {...(c.cleared_by_name || c.bounced_by_name
            ? { description: `By ${c.cleared_by_name ?? c.bounced_by_name}` }
            : {})}
        />
      </div>

      {c.status === 'Cleared' ? (
        <p className="text-sm text-muted-foreground">
          {c.affects_balance
            ? `${c.bank} was reduced by ${formatAED(c.amount)} on the cheque date (${formatDate(c.cheque_date)}).`
            : 'This cheque is dated before financial tracking started, so it does not change the bank balance.'}
        </p>
      ) : null}
      {c.status === 'Bounced' ? (
        <p className="text-sm text-muted-foreground">
          No bank deduction was made.{' '}
          {c.replaced_by_id ? (
            <>
              Replaced by cheque{' '}
              <Link
                className="text-primary hover:underline"
                to={`/pdc-cheques/${c.replaced_by_id}`}
              >
                {c.replaced_by_no}
              </Link>
              .
            </>
          ) : (
            'A replacement cheque is still needed.'
          )}
        </p>
      ) : null}
      {c.replaces_id ? (
        <p className="text-sm text-muted-foreground">
          This cheque replaces bounced cheque{' '}
          <Link className="text-primary hover:underline" to={`/pdc-cheques/${c.replaces_id}`}>
            {c.replaces_no}
          </Link>
          .
        </p>
      ) : null}

      <SectionCard title="Rental agreement">
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-muted-foreground">Agreement</dt>
            <dd>
              <Link to={`/rentals/${a.id}`} className="font-medium text-primary hover:underline">
                {a.unit ?? a.landlord}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Period</dt>
            <dd>
              {formatDate(a.start_date)} – {formatDate(a.end_date)}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Annual rent</dt>
            <dd>{formatAED(a.annual_rent)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Agreement status</dt>
            <dd>
              <AgreementBadge status={a.status} />
            </dd>
          </div>
        </dl>
      </SectionCard>

      {c.notes ? (
        <SectionCard title="Notes">
          <p className="text-sm whitespace-pre-wrap">{c.notes}</p>
        </SectionCard>
      ) : null}

      <SectionCard
        title="Change history"
        description="Every status change and edit, who made it and why."
      >
        <ChequeHistory entries={detail.data.history} />
      </SectionCard>
    </PageContainer>
  )
}
