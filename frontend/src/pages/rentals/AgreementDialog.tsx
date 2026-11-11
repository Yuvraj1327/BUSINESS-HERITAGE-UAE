import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { FormTextarea } from '@/components/forms/form-textarea'
import { useBranchContext } from '@/components/layout/branch-context'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useCreateAgreement, useSchedulePreview, useUpdateAgreement } from '@/hooks/use-rentals'
import { toApiError } from '@/lib/errors'
import {
  agreementEditSchema,
  agreementFormSchema,
  RENTAL_BANKS,
  type Agreement,
  type AgreementEditInput,
  type AgreementFormInput,
  type AgreementFormValues,
  type SchedulePreview,
} from '@/schemas/rentals'
import { formatDate } from '@/utils/format'
import { defaultEndDate } from './helpers'
import { SchedulePreviewTable } from './shared'

const blank: AgreementFormInput = {
  branch_id: '',
  landlord: '',
  unit: '',
  start_date: '',
  end_date: '',
  annual_rent: '',
  cheque_count: '',
  first_cheque_date: '',
  first_cheque_no: '',
  bank: 'ENBD',
  notes: '',
}
const countOptions = Array.from({ length: 12 }, (_, i) => ({
  value: String(i + 1),
  label: String(i + 1),
}))
const bankOptions = RENTAL_BANKS.map((b) => ({ value: b, label: b }))

/* ---------- add: fill in -> preview the generated schedule -> confirm (nothing is saved before the confirmation) ---------- */
function AddForm({ onSaved, onDone }: { onSaved?: (id: string) => void; onDone: () => void }) {
  const { branches } = useBranchContext()
  const form = useForm<AgreementFormInput, unknown, AgreementFormValues>({
    resolver: zodResolver(agreementFormSchema),
    defaultValues: blank,
  })
  const create = useCreateAgreement()
  const previewMut = useSchedulePreview()
  const [preview, setPreview] = useState<{ key: string; data: SchedulePreview } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState
  const watched = useWatch({ control: form.control })
  const key = JSON.stringify(watched)
  const fresh = preview !== null && preview.key === key
  const start = watched.start_date ?? ''

  function body(v: AgreementFormValues) {
    return {
      annual_rent: v.annual_rent,
      cheque_count: Number(v.cheque_count),
      first_cheque_date: v.first_cheque_date,
      first_cheque_no: v.first_cheque_no,
      bank: v.bank,
    }
  }

  async function submit(v: AgreementFormValues) {
    setError(null)
    try {
      if (!fresh) {
        const data = await previewMut.mutateAsync(body(v))
        setPreview({ key: JSON.stringify(form.getValues()), data })
        return
      }
      const saved = await create.mutateAsync({
        ...body(v),
        branch_id: v.branch_id,
        landlord: v.landlord,
        start_date: v.start_date,
        ...(v.unit ? { unit: v.unit } : {}),
        ...(v.end_date ? { end_date: v.end_date } : {}),
        ...(v.notes ? { notes: v.notes } : {}),
        // The Owner confirms exactly the schedule that was reviewed.
        cheques: preview.data.lines.map((l) => ({
          cheque_no: l.cheque_no,
          cheque_date: l.cheque_date,
          amount: l.amount,
          bank: l.bank,
        })),
      })
      toast.success('Rental agreement saved')
      onSaved?.(saved.agreement.id)
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in blank) form.setError(field as keyof AgreementFormInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }

  return (
    <form
      noValidate
      aria-label="Rental agreement form"
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
      <div className="grid gap-4 sm:grid-cols-2">
        <Controller
          control={form.control}
          name="branch_id"
          render={({ field }) => (
            <FormSelect
              label="Branch"
              required
              value={field.value || ''}
              onValueChange={field.onChange}
              options={branches
                .filter((b) => b.is_active)
                .map((b) => ({ value: b.id, label: b.name }))}
              error={errors.branch_id}
            />
          )}
        />
        <FormInput
          label="Landlord name"
          required
          maxLength={150}
          error={errors.landlord}
          {...form.register('landlord')}
        />
      </div>
      <FormInput
        label="Rental unit / property details"
        maxLength={200}
        error={errors.unit}
        {...form.register('unit')}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormDatePicker
          label="Start date"
          required
          error={errors.start_date}
          {...form.register('start_date')}
        />
        <FormDatePicker
          label="End date"
          description={
            start
              ? `Leave blank for ${formatDate(defaultEndDate(start))} (start + 12 months - 1 day).`
              : 'Leave blank for start + 12 months - 1 day.'
          }
          error={errors.end_date}
          {...form.register('end_date')}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <FormInput
          label="Annual rent (AED)"
          required
          inputMode="decimal"
          autoComplete="off"
          error={errors.annual_rent}
          {...form.register('annual_rent')}
        />
        <Controller
          control={form.control}
          name="cheque_count"
          render={({ field }) => (
            <FormSelect
              label="Number of cheques"
              required
              value={field.value || ''}
              onValueChange={field.onChange}
              options={countOptions}
              error={errors.cheque_count}
            />
          )}
        />
        <Controller
          control={form.control}
          name="bank"
          render={({ field }) => (
            <FormSelect
              label="Bank"
              required
              value={field.value || ''}
              onValueChange={field.onChange}
              options={bankOptions}
              error={errors.bank}
            />
          )}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormDatePicker
          label="First cheque date"
          required
          error={errors.first_cheque_date}
          {...form.register('first_cheque_date')}
        />
        <FormInput
          label="First cheque number"
          required
          maxLength={50}
          description="Must end in digits: the next cheques continue the number."
          error={errors.first_cheque_no}
          {...form.register('first_cheque_no')}
        />
      </div>
      <FormTextarea
        label="Notes"
        maxLength={1000}
        error={errors.notes}
        {...form.register('notes')}
      />

      {fresh ? (
        <div className="space-y-2" aria-live="polite">
          <h3 className="text-sm font-semibold">Review the cheque schedule</h3>
          <p className="text-sm text-muted-foreground">
            Cheque dates are the first cheque date plus rounded months; the last cheque takes the
            remainder so the total equals the rent. Nothing is saved until you confirm.
          </p>
          <SchedulePreviewTable preview={preview.data} caption="Generated cheque schedule" />
        </div>
      ) : preview ? (
        <p role="status" className="text-sm text-warning">
          The details changed. Preview the schedule again before confirming.
        </p>
      ) : null}

      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={previewMut.isPending || create.isPending}>
          {previewMut.isPending || create.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : null}
          {fresh ? 'Confirm agreement and schedule' : 'Preview schedule'}
        </Button>
      </div>
    </form>
  )
}

/* ---------- edit: only details that do not change money. Rent, cheques and bank change through replacement or renewal. ---------- */
function EditForm({ agreement, onDone }: { agreement: Agreement; onDone: () => void }) {
  const { branches } = useBranchContext()
  const update = useUpdateAgreement()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<AgreementEditInput>({
    resolver: zodResolver(agreementEditSchema),
    defaultValues: {
      branch_id: agreement.branch_id,
      landlord: agreement.landlord,
      unit: agreement.unit ?? '',
      start_date: agreement.start_date,
      end_date: agreement.end_date,
      notes: agreement.notes ?? '',
      reason: '',
    },
  })
  const { errors } = form.formState
  const [branch, startD, endD] = useWatch({
    control: form.control,
    name: ['branch_id', 'start_date', 'end_date'],
  })
  const sensitive =
    branch !== agreement.branch_id || startD !== agreement.start_date || endD !== agreement.end_date

  async function submit(v: AgreementEditInput) {
    setError(null)
    if (sensitive && v.reason.length < 3) {
      form.setError('reason', { message: 'Enter a reason (at least 3 characters)' })
      return
    }
    try {
      await update.mutateAsync({
        id: agreement.id,
        body: {
          branch_id: v.branch_id,
          landlord: v.landlord,
          start_date: v.start_date,
          end_date: v.end_date,
          ...(v.unit ? { unit: v.unit } : {}),
          ...(v.notes ? { notes: v.notes } : {}),
          ...(sensitive && v.reason ? { reason: v.reason } : {}),
        },
      })
      toast.success('Agreement updated')
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in v) form.setError(field as keyof AgreementEditInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }
  return (
    <form
      noValidate
      aria-label="Rental agreement form"
      className="space-y-4"
      onSubmit={form.handleSubmit(submit)}
    >
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Controller
          control={form.control}
          name="branch_id"
          render={({ field }) => (
            <FormSelect
              label="Branch"
              required
              value={field.value || ''}
              onValueChange={field.onChange}
              options={branches
                .filter((b) => b.is_active)
                .map((b) => ({ value: b.id, label: b.name }))}
              error={errors.branch_id}
            />
          )}
        />
        <FormInput
          label="Landlord name"
          required
          maxLength={150}
          error={errors.landlord}
          {...form.register('landlord')}
        />
      </div>
      <FormInput
        label="Rental unit / property details"
        maxLength={200}
        error={errors.unit}
        {...form.register('unit')}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormDatePicker
          label="Start date"
          required
          error={errors.start_date}
          {...form.register('start_date')}
        />
        <FormDatePicker
          label="End date"
          required
          error={errors.end_date}
          {...form.register('end_date')}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Annual rent, number of cheques, bank and the cheque schedule cannot be edited here. Change a
        cheque from the PDC Cheques screen, replace a bounced cheque, or renew the agreement.
      </p>
      <FormTextarea
        label="Notes"
        maxLength={1000}
        error={errors.notes}
        {...form.register('notes')}
      />
      {sensitive ? (
        <FormTextarea
          label="Reason for the change"
          required
          maxLength={500}
          description="Branch and date changes are kept in the audit history."
          error={errors.reason}
          {...form.register('reason')}
        />
      ) : null}
      <FormActions submitLabel="Save changes" isSubmitting={update.isPending} onCancel={onDone} />
    </form>
  )
}

export function AgreementDialog({
  open,
  onOpenChange,
  agreement,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  agreement?: Agreement | null
  onSaved?: (id: string) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{agreement ? 'Edit rental agreement' : 'Add rental agreement'}</DialogTitle>
          <DialogDescription>
            {agreement
              ? 'Update the details of an active agreement.'
              : 'Enter the agreement, then review the generated PDC cheque schedule before confirming.'}
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so every opening starts clean. */}
        {open ? (
          agreement ? (
            <EditForm agreement={agreement} onDone={() => onOpenChange(false)} />
          ) : (
            <AddForm {...(onSaved ? { onSaved } : {})} onDone={() => onOpenChange(false)} />
          )
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
