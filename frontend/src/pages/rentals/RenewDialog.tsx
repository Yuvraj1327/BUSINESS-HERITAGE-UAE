import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useRenewAgreement, useRenewalPreview } from '@/hooks/use-rentals'
import { toApiError } from '@/lib/errors'
import {
  renewFormSchema,
  RENTAL_BANKS,
  type Agreement,
  type RenewalPreview,
  type RenewFormInput,
} from '@/schemas/rentals'
import type { RenewPayload } from '@/services/rentals.service'
import { formatAED, formatDate } from '@/utils/format'
import { SchedulePreviewTable } from './shared'

const blank: RenewFormInput = {
  annual_rent: '',
  cheque_count: '',
  first_cheque_date: '',
  first_cheque_no: '',
  bank: '',
}
const countOptions = [
  { value: '', label: 'Same as before' },
  ...Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) })),
]
const bankOptions = [
  { value: '', label: 'Same as before' },
  ...RENTAL_BANKS.map((b) => ({ value: b, label: b })),
]

function payload(v: RenewFormInput): RenewPayload {
  return {
    ...(v.annual_rent ? { annual_rent: v.annual_rent } : {}),
    ...(v.cheque_count ? { cheque_count: Number(v.cheque_count) } : {}),
    ...(v.first_cheque_date ? { first_cheque_date: v.first_cheque_date } : {}),
    ...(v.first_cheque_no ? { first_cheque_no: v.first_cheque_no } : {}),
    ...(v.bank ? { bank: v.bank as 'ENBD' | 'ADCB' } : {}),
  }
}

function Row({ label, before, after }: { label: string; before: string; after: string }) {
  return (
    <tr className="border-t">
      <th scope="row" className="py-1.5 pr-4 text-left font-normal text-muted-foreground">
        {label}
      </th>
      <td className="py-1.5 pr-4">{before}</td>
      <td className="py-1.5 font-medium">{after}</td>
    </tr>
  )
}

function RenewForm({ agreement, onDone }: { agreement: Agreement; onDone: () => void }) {
  const form = useForm<RenewFormInput>({
    resolver: zodResolver(renewFormSchema),
    defaultValues: blank,
  })
  const previewMut = useRenewalPreview()
  const renew = useRenewAgreement()
  const [preview, setPreview] = useState<{ key: string; data: RenewalPreview } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState
  const watched = useWatch({ control: form.control })
  const fresh = preview !== null && preview.key === JSON.stringify(watched)

  async function submit(v: RenewFormInput) {
    setError(null)
    try {
      if (!fresh) {
        const data = await previewMut.mutateAsync({ id: agreement.id, body: payload(v) })
        setPreview({ key: JSON.stringify(form.getValues()), data })
        return
      }
      // The overrides were already validated by the preview; the Owner confirms exactly what was reviewed.
      await renew.mutateAsync({
        id: agreement.id,
        body: {
          ...payload(v),
          first_cheque_no: preview.data.first_cheque_no,
          first_cheque_date: preview.data.first_cheque_date,
          expected_end_date: agreement.end_date,
        },
      })
      toast.success('Agreement renewed')
      onDone()
    } catch (e) {
      setError(toApiError(e).message)
    }
  }
  const p = preview?.data
  return (
    <form
      noValidate
      aria-label="Renew agreement"
      className="space-y-4"
      onSubmit={form.handleSubmit(submit)}
    >
      {error ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}
      <p className="text-sm text-muted-foreground">
        The new agreement starts the day after this one ends. Leave a field blank to keep the same
        rent, cheque count and bank; cheque numbering continues from the old series.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormInput
          label="New annual rent (AED)"
          inputMode="decimal"
          autoComplete="off"
          placeholder={agreement.annual_rent}
          error={errors.annual_rent}
          {...form.register('annual_rent')}
        />
        <Controller
          control={form.control}
          name="cheque_count"
          render={({ field }) => (
            <FormSelect
              label="Number of cheques"
              value={field.value || ''}
              onValueChange={field.onChange}
              options={countOptions}
              error={errors.cheque_count}
            />
          )}
        />
        <FormDatePicker
          label="First cheque date"
          description="Leave blank for the new start date."
          error={errors.first_cheque_date}
          {...form.register('first_cheque_date')}
        />
        <FormInput
          label="First cheque number"
          description="Leave blank to continue the old series."
          maxLength={50}
          error={errors.first_cheque_no}
          {...form.register('first_cheque_no')}
        />
        <Controller
          control={form.control}
          name="bank"
          render={({ field }) => (
            <FormSelect
              label="Bank"
              value={field.value || ''}
              onValueChange={field.onChange}
              options={bankOptions}
              error={errors.bank}
            />
          )}
        />
      </div>

      {fresh && p ? (
        <div className="space-y-3" aria-live="polite">
          <h3 className="text-sm font-semibold">Old and new agreement</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1 pr-4 font-normal">&nbsp;</th>
                <th className="py-1 pr-4 font-normal">Current</th>
                <th className="py-1 font-normal">Renewed</th>
              </tr>
            </thead>
            <tbody>
              <Row
                label="Start date"
                before={formatDate(agreement.start_date)}
                after={formatDate(p.start_date)}
              />
              <Row
                label="End date"
                before={formatDate(agreement.end_date)}
                after={formatDate(p.end_date)}
              />
              <Row
                label="Annual rent"
                before={formatAED(p.old_annual_rent)}
                after={formatAED(p.annual_rent)}
              />
              <Row
                label="Cheques"
                before={String(agreement.cheque_count ?? agreement.live_cheques)}
                after={String(p.cheque_count)}
              />
              <Row label="Bank" before={agreement.bank ?? '—'} after={p.bank} />
              <Row
                label="First cheque number"
                before={agreement.first_cheque_no ?? '—'}
                after={p.first_cheque_no}
              />
            </tbody>
          </table>
          {p.old_pending_cheques > 0 ? (
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
              {p.old_pending_cheques} pending cheque{p.old_pending_cheques === 1 ? '' : 's'} on the
              current agreement stay Pending. Renewing never clears or deletes them.
            </p>
          ) : null}
          <SchedulePreviewTable preview={p.schedule} caption="New cheque schedule" />
        </div>
      ) : preview ? (
        <p role="status" className="text-sm text-warning">
          The details changed. Preview the renewal again before confirming.
        </p>
      ) : null}

      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={previewMut.isPending || renew.isPending}>
          {previewMut.isPending || renew.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : null}
          {fresh ? 'Confirm renewal' : 'Preview renewal'}
        </Button>
      </div>
    </form>
  )
}

export function RenewDialog({
  open,
  onOpenChange,
  agreement,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  agreement: Agreement
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Renew agreement</DialogTitle>
          <DialogDescription>
            {agreement.branch_name} · {agreement.landlord}. Ends {formatDate(agreement.end_date)}.
            The current agreement and its cheques are kept and linked to the renewal.
          </DialogDescription>
        </DialogHeader>
        {open ? <RenewForm agreement={agreement} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  )
}
