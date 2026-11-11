import { zodResolver } from '@hookform/resolvers/zod'
import { Archive, ArrowLeft, Loader2, Pencil, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormInput } from '@/components/forms/form-input'
import { FormTextarea } from '@/components/forms/form-textarea'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useArchiveLicense, useLicense, useRenewLicense } from '@/hooks/use-hr'
import { toApiError } from '@/lib/errors'
import { aedAmountSchema } from '@/schemas/common'
import type { License, Renewal } from '@/schemas/hr'
import { formatAED, formatDate } from '@/utils/format'
import { LicenseDialog } from './LicenseDialog'
import { previewRenewal } from './helpers'
import { ActionDialog, ChangeHistory, ExpiryBadge } from './shared'

const renewSchema = z.object({
  fee: z.string().trim().min(1, 'Enter the renewal fee').pipe(aedAmountSchema),
  note: z.string().trim().max(500),
})

function RenewForm({ license, onDone }: { license: License; onDone: () => void }) {
  const renew = useRenewLicense()
  // One key per opening of the dialog: a double click or retry can never record the renewal twice.
  const [clientKey] = useState(() => crypto.randomUUID())
  const [error, setError] = useState<string | null>(null)
  const form = useForm({
    resolver: zodResolver(renewSchema),
    defaultValues: { fee: license.renewal_fee, note: '' },
  })
  const { errors, isSubmitting } = form.formState
  const next = previewRenewal(license.expiry_date)
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={form.handleSubmit(async (v) => {
        setError(null)
        try {
          await renew.mutateAsync({
            id: license.id,
            body: {
              expected_expiry: license.expiry_date,
              renewal_fee: v.fee,
              client_key: clientKey,
              ...(v.note ? { note: v.note } : {}),
            },
          })
          toast.success('Licence renewed')
          onDone()
        } catch (e) {
          setError(toApiError(e).message)
        }
      })}
    >
      <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
        Expiry moves from <strong>{formatDate(license.expiry_date)}</strong> to{' '}
        <strong>{formatDate(next)}</strong> (one year added to the current expiry). The previous
        expiry stays in the renewal history.
      </p>
      <FormInput
        label="Renewal fee paid (AED)"
        required
        inputMode="decimal"
        autoComplete="off"
        description="Recorded with this renewal. It does not create an expense; record that under Expenses."
        error={errors.fee}
        {...form.register('fee')}
      />
      <FormTextarea label="Note" maxLength={500} error={errors.note} {...form.register('note')} />
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? <Loader2 className="animate-spin" aria-hidden /> : null}
          Confirm renewal
        </Button>
      </DialogFooter>
    </form>
  )
}

export function LicenseDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const detail = useLicense(id)
  const archive = useArchiveLicense()
  const [editing, setEditing] = useState(false)
  const [renewing, setRenewing] = useState(false)
  const [archiving, setArchiving] = useState(false)

  if (detail.isLoading) return <LoadingState label="Loading licence…" />
  if (detail.error || !detail.data)
    return (
      <PageContainer title="Trade licence">
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      </PageContainer>
    )
  const l = detail.data.license

  const columns: DataTableColumn<Renewal>[] = [
    { key: 'd', header: 'Renewed on', cell: (r) => formatDate(r.renewed_on) },
    { key: 'p', header: 'Previous expiry', cell: (r) => formatDate(r.previous_expiry) },
    { key: 'n', header: 'New expiry', cell: (r) => formatDate(r.new_expiry) },
    { key: 'f', header: 'Fee', align: 'right', cell: (r) => formatAED(r.renewal_fee) },
    { key: 'b', header: 'By', cell: (r) => r.created_by_name ?? '—' },
    { key: 'x', header: 'Note', cell: (r) => r.note ?? '—', className: 'max-w-48 truncate' },
  ]

  return (
    <PageContainer
      title={`Licence ${l.license_no}`}
      description={`${l.branch_name}${l.authority ? ` · ${l.authority}` : ''}`}
      actions={
        <>
          <Button variant="outline" asChild>
            <Link to="/trade-licenses">
              <ArrowLeft aria-hidden /> All licences
            </Link>
          </Button>
          <Can module="trade_licenses" action="update">
            <Button variant="outline" onClick={() => setEditing(true)} disabled={l.archived}>
              <Pencil aria-hidden /> Edit
            </Button>
          </Can>
        </>
      }
    >
      {l.archived ? (
        <p className="text-sm text-muted-foreground">This licence is archived.</p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Expiry date" value={formatDate(l.expiry_date)} />
        <StatCard
          label="Status"
          value={<ExpiryBadge status={l.status} days={l.days_remaining} />}
        />
        <StatCard label="Renewal fee" value={formatAED(l.renewal_fee)} />
        <StatCard
          label="Renewals recorded"
          value={String(l.renewal_count)}
          {...(l.last_renewed_on
            ? { description: `Last on ${formatDate(l.last_renewed_on)}` }
            : {})}
        />
      </div>

      <Can module="trade_licenses" action="update">
        {!l.archived ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setRenewing(true)}>
              <RefreshCw aria-hidden /> Mark as renewed
            </Button>
            <Button variant="outline" onClick={() => setArchiving(true)}>
              <Archive aria-hidden /> Archive
            </Button>
          </div>
        ) : null}
      </Can>

      {l.notes ? (
        <SectionCard title="Notes">
          <p className="text-sm whitespace-pre-wrap">{l.notes}</p>
        </SectionCard>
      ) : null}

      <SectionCard
        title="Renewal history"
        description="Newest first. Past renewals are never changed."
      >
        <DataTable
          caption="Renewal history"
          rows={detail.data.renewals}
          getRowId={(r) => r.id}
          columns={columns}
          emptyTitle="No renewals recorded yet"
        />
      </SectionCard>

      <SectionCard title="Change history" description="Every edit, who made it and why.">
        <ChangeHistory entries={detail.data.history} />
      </SectionCard>

      <LicenseDialog open={editing} onOpenChange={setEditing} license={l} />
      <Dialog open={renewing} onOpenChange={setRenewing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mark licence as renewed?</DialogTitle>
            <DialogDescription>
              {l.branch_name} · {l.license_no}. This records the renewal once; a second click on the
              same screen is refused.
            </DialogDescription>
          </DialogHeader>
          {renewing ? <RenewForm license={l} onDone={() => setRenewing(false)} /> : null}
        </DialogContent>
      </Dialog>
      {archiving ? (
        <ActionDialog
          open
          onOpenChange={(o) => !o && setArchiving(false)}
          title="Archive this licence?"
          description="Licences are never deleted. An archived licence is hidden from lists, fees due and alerts; its history stays."
          destructive
          confirmLabel="Archive"
          onSubmit={async (v) => {
            await archive.mutateAsync({ id, reason: v.reason })
            toast.success('Licence archived')
            navigate('/trade-licenses')
          }}
        />
      ) : null}
    </PageContainer>
  )
}
