import { zodResolver } from '@hookform/resolvers/zod'
import { History, Landmark, Lock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useFieldArray, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { EmptyState } from '@/components/common/empty-state'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { SectionCard } from '@/components/common/section-card'
import { StatusBadge } from '@/components/common/status-badge'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { FormTextarea } from '@/components/forms/form-textarea'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useOpeningBalances, useOpeningHistory, useSaveOpeningBalances } from '@/hooks/use-finance'
import { toApiError } from '@/lib/errors'
import {
  openingFormSchema,
  type AuditEntry,
  type OpeningBalances,
  type OpeningFormInput,
  type OpeningFormValues,
} from '@/schemas/finance'
import { dubaiToday, formatAED, formatDate } from '@/utils/format'

const toForm = (o: OpeningBalances): OpeningFormInput => ({
  as_of_date: o.as_of_date ?? dubaiToday(),
  receipts_bank: o.receipts_bank ?? ('' as 'ENBD'),
  enbd_balance: o.enbd_balance,
  adcb_balance: o.adcb_balance,
  pos_pending: o.pos_pending,
  savings_brought_forward: o.savings_brought_forward,
  branch_cash: o.branch_cash.map((b) => ({ branch_id: b.branch_id, amount: b.amount })),
  supplier_dues: o.supplier_dues.map((s) => ({ supplier_id: s.supplier_id, amount: s.amount })),
  reason: '',
})

function nextDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 1)
  return d.toISOString().slice(0, 10)
}

const sum = (xs: { amount: string }[]) => xs.reduce((t, x) => t + (Number(x.amount) || 0), 0)

export function OpeningBalancesPage() {
  const query = useOpeningBalances()
  const save = useSaveOpeningBalances()
  const [pending, setPending] = useState<OpeningFormValues | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const history = useOpeningHistory(showHistory)

  const data = query.data
  const configured = data?.status === 'configured'
  const form = useForm<OpeningFormInput, unknown, OpeningFormValues>({
    resolver: zodResolver(openingFormSchema),
    defaultValues: { as_of_date: dubaiToday(), branch_cash: [], supplier_dues: [], reason: '' },
  })
  const branchRows = useFieldArray({ control: form.control, name: 'branch_cash' })
  const supplierRows = useFieldArray({ control: form.control, name: 'supplier_dues' })
  const { errors } = form.formState
  const watch = useWatch({ control: form.control })

  useEffect(() => {
    if (data) form.reset(toForm(data))
  }, [data, form])

  if (query.isLoading) return <LoadingState label="Loading opening balances…" />
  if (query.error || !data)
    return (
      <PageContainer title="Opening Balances">
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </PageContainer>
    )

  const nameOfBranch = (id: string) =>
    data.branch_cash.find((b) => b.branch_id === id)?.branch_name ?? id
  const nameOfSupplier = (id: string) =>
    data.supplier_dues.find((s) => s.supplier_id === id)?.supplier_name ?? id

  function submit(values: OpeningFormValues) {
    setFormError(null)
    if (configured && !values.reason) {
      form.setError('reason', { message: 'A reason is required to change saved opening balances' })
      return
    }
    setPending(values)
  }

  async function confirm() {
    if (!pending) return
    try {
      await save.mutateAsync({
        as_of_date: pending.as_of_date,
        receipts_bank: pending.receipts_bank,
        enbd_balance: pending.enbd_balance,
        adcb_balance: pending.adcb_balance,
        pos_pending: pending.pos_pending,
        savings_brought_forward: pending.savings_brought_forward,
        branch_cash: pending.branch_cash,
        supplier_dues: pending.supplier_dues,
        ...(pending.reason ? { reason: pending.reason } : {}),
      })
      toast.success(configured ? 'Opening balances corrected' : 'Opening balances saved')
      setPending(null)
    } catch (e) {
      const err = toApiError(e)
      setPending(null)
      setFormError(err.message)
      toast.error(err.message)
    }
  }

  const lockedDate = configured && data.date_locked

  return (
    <PageContainer
      title="Opening Balances"
      description="Starting cash, bank, POS, savings and supplier dues. Tracking begins the day after the as-of date."
      actions={
        configured ? (
          <StatusBadge status="success">Configured</StatusBadge>
        ) : (
          <StatusBadge status="warning">Not configured</StatusBadge>
        )
      }
    >
      {!configured ? (
        <EmptyState
          icon={Landmark}
          title="Opening balances are not set up yet"
          description="Cash & Banks, expenses and supplier payments stay unavailable until you review and save the starting balances below."
        />
      ) : (
        <SectionCard title="Current configuration">
          <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">As of</dt>
              <dd className="font-medium">{formatDate(data.as_of_date as string)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Tracking starts</dt>
              <dd className="font-medium">{formatDate(data.tracking_start as string)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last saved by</dt>
              <dd className="font-medium">{data.updated_by_name ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last saved at</dt>
              <dd className="font-medium">
                {data.updated_at
                  ? new Date(data.updated_at).toLocaleString('en-GB', { timeZone: 'Asia/Dubai' })
                  : '—'}
              </dd>
            </div>
          </dl>
        </SectionCard>
      )}

      <form
        onSubmit={form.handleSubmit(submit)}
        noValidate
        aria-label="Opening balances form"
        className="space-y-6"
      >
        {formError ? (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          >
            {formError}
          </p>
        ) : null}

        <SectionCard title="As-of date and receiving bank">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormDatePicker
              label="Opening balance as of"
              required
              max={dubaiToday()}
              disabled={lockedDate}
              description={
                lockedDate
                  ? 'Locked: transactions already exist after this date.'
                  : watch.as_of_date
                    ? `Tracking starts ${formatDate(nextDay(watch.as_of_date))}`
                    : undefined
              }
              error={errors.as_of_date}
              {...form.register('as_of_date')}
            />
            <Controller
              control={form.control}
              name="receipts_bank"
              render={({ field }) => (
                <FormSelect
                  label="Bank that receives bank transfers and payment links"
                  required
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  options={[
                    { value: 'ENBD', label: 'ENBD' },
                    { value: 'ADCB', label: 'ADCB' },
                  ]}
                  placeholder="Select bank"
                  error={errors.receipts_bank}
                />
              )}
            />
          </div>
          {lockedDate ? (
            <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
              <Lock className="size-4" aria-hidden /> The date can only change while no transactions
              exist.
            </p>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Bank, POS and savings"
          description="Amounts in AED. Zero is allowed; negative amounts are not."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormInput
              label="ENBD balance (AED)"
              inputMode="decimal"
              autoComplete="off"
              error={errors.enbd_balance}
              {...form.register('enbd_balance')}
            />
            <FormInput
              label="ADCB balance (AED)"
              inputMode="decimal"
              autoComplete="off"
              error={errors.adcb_balance}
              {...form.register('adcb_balance')}
            />
            <FormInput
              label="POS pending (AED)"
              inputMode="decimal"
              autoComplete="off"
              error={errors.pos_pending}
              {...form.register('pos_pending')}
            />
            <FormInput
              label="Savings brought forward (AED)"
              inputMode="decimal"
              autoComplete="off"
              error={errors.savings_brought_forward}
              {...form.register('savings_brought_forward')}
            />
          </div>
        </SectionCard>

        <SectionCard
          title="Branch cash"
          description="Cash in hand at each branch on the as-of date."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {branchRows.fields.map((f, i) => (
              <FormInput
                key={f.id}
                label={`${nameOfBranch(f.branch_id)} (AED)`}
                inputMode="decimal"
                autoComplete="off"
                error={errors.branch_cash?.[i]?.amount}
                {...form.register(`branch_cash.${i}.amount`)}
              />
            ))}
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            Total branch cash:{' '}
            <span className="font-medium text-foreground tabular">
              {formatAED(sum((watch.branch_cash ?? []).map((b) => ({ amount: b?.amount ?? '' }))))}
            </span>
          </p>
        </SectionCard>

        <SectionCard
          title="Supplier opening dues"
          description="What each supplier was owed on the as-of date. Later dues and payments are recorded separately."
        >
          {supplierRows.fields.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No suppliers yet. Add suppliers first, then return here to set their opening dues.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {supplierRows.fields.map((f, i) => (
                <FormInput
                  key={f.id}
                  label={`${nameOfSupplier(f.supplier_id)} (AED)`}
                  inputMode="decimal"
                  autoComplete="off"
                  error={errors.supplier_dues?.[i]?.amount}
                  {...form.register(`supplier_dues.${i}.amount`)}
                />
              ))}
            </div>
          )}
        </SectionCard>

        {configured ? (
          <SectionCard title="Reason for the change">
            <FormTextarea
              label="Why are the saved balances being changed?"
              required
              maxLength={500}
              description="Saved balances are never overwritten silently: the old values and this reason go to the audit log."
              error={errors.reason}
              {...form.register('reason')}
            />
          </SectionCard>
        ) : null}

        <FormActions
          submitLabel={configured ? 'Review changes' : 'Review & save'}
          isSubmitting={save.isPending}
          onCancel={() => data && form.reset(toForm(data))}
          cancelLabel="Reset"
        />
      </form>

      {configured ? (
        <SectionCard
          title="Change history"
          actions={
            <Button variant="outline" size="sm" onClick={() => setShowHistory((v) => !v)}>
              <History aria-hidden /> {showHistory ? 'Hide' : 'Show'} history
            </Button>
          }
        >
          {showHistory ? (
            <DataTable<AuditEntry>
              caption="Opening balance change history"
              rows={history.data}
              isLoading={history.isLoading}
              error={history.error}
              onRetry={() => void history.refetch()}
              getRowId={(r) => String(r.id)}
              emptyTitle="No changes recorded"
              columns={historyColumns}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Every save and correction is recorded with who, when and why.
            </p>
          )}
        </SectionCard>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={
          configured ? 'Confirm the corrected opening balances' : 'Confirm the opening balances'
        }
        confirmLabel={configured ? 'Save correction' : 'Save opening balances'}
        isLoading={save.isPending}
        onConfirm={confirm}
        description={
          pending ? (
            <div className="space-y-2 text-left text-sm" data-testid="opening-review">
              <p>
                As of <strong>{formatDate(pending.as_of_date)}</strong>; tracking starts{' '}
                <strong>{formatDate(nextDay(pending.as_of_date))}</strong>. Bank receipts go to{' '}
                <strong>{pending.receipts_bank}</strong>.
              </p>
              <ul className="space-y-1">
                <li>Branch cash: {formatAED(sum(pending.branch_cash))}</li>
                <li>ENBD: {formatAED(pending.enbd_balance)}</li>
                <li>ADCB: {formatAED(pending.adcb_balance)}</li>
                <li>POS pending: {formatAED(pending.pos_pending)}</li>
                <li>Savings brought forward: {formatAED(pending.savings_brought_forward)}</li>
                <li>Supplier dues: {formatAED(sum(pending.supplier_dues))}</li>
              </ul>
              <p className="text-muted-foreground">
                This is recorded with your name and the time.
                {pending.reason ? ` Reason: ${pending.reason}` : ''}
              </p>
            </div>
          ) : null
        }
      />
    </PageContainer>
  )
}

const historyColumns: DataTableColumn<AuditEntry>[] = [
  {
    key: 'when',
    header: 'When',
    cell: (r) => new Date(r.occurred_at).toLocaleString('en-GB', { timeZone: 'Asia/Dubai' }),
  },
  { key: 'who', header: 'By', cell: (r) => r.actor_name ?? '—' },
  {
    key: 'what',
    header: 'Change',
    cell: (r) => `${r.action} · ${r.table_name.replaceAll('_', ' ')}`,
  },
  { key: 'reason', header: 'Reason', cell: (r) => r.reason ?? '—' },
]
