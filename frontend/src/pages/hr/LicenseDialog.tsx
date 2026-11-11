import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { FormTextarea } from '@/components/forms/form-textarea'
import { useBranchContext } from '@/components/layout/branch-context'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useCreateLicense, useUpdateLicense } from '@/hooks/use-hr'
import { toApiError } from '@/lib/errors'
import {
  licenseFormSchema,
  type License,
  type LicenseFormInput,
  type LicenseFormValues,
} from '@/schemas/hr'

const blank: LicenseFormInput = {
  branch_id: '',
  license_no: '',
  authority: '',
  expiry_date: '',
  renewal_fee: '',
  notes: '',
  reason: '',
}

function LicenseForm({
  license,
  onSaved,
  onDone,
}: {
  license?: License | null
  onSaved?: (id: string) => void
  onDone: () => void
}) {
  const { branches } = useBranchContext()
  const form = useForm<LicenseFormInput, unknown, LicenseFormValues>({
    resolver: zodResolver(licenseFormSchema),
    defaultValues: license
      ? {
          branch_id: license.branch_id,
          license_no: license.license_no,
          authority: license.authority ?? '',
          expiry_date: license.expiry_date,
          renewal_fee: license.renewal_fee,
          notes: license.notes ?? '',
          reason: '',
        }
      : blank,
  })
  const create = useCreateLicense()
  const update = useUpdateLicense()
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState
  const [branch, no, expiry, fee] = useWatch({
    control: form.control,
    name: ['branch_id', 'license_no', 'expiry_date', 'renewal_fee'],
  })
  const sensitive =
    !!license &&
    (branch !== license.branch_id ||
      no !== license.license_no ||
      expiry !== license.expiry_date ||
      fee !== license.renewal_fee)

  async function submit(v: LicenseFormValues) {
    setError(null)
    if (sensitive && v.reason.length < 3) {
      form.setError('reason', { message: 'Enter a reason (at least 3 characters)' })
      return
    }
    const body = {
      branch_id: v.branch_id,
      license_no: v.license_no,
      expiry_date: v.expiry_date,
      renewal_fee: v.renewal_fee,
      ...(v.authority ? { authority: v.authority } : {}),
      ...(v.notes ? { notes: v.notes } : {}),
      ...(sensitive && v.reason ? { reason: v.reason } : {}),
    }
    try {
      const saved = license
        ? await update.mutateAsync({ id: license.id, body })
        : await create.mutateAsync(body)
      toast.success(license ? 'Licence updated' : 'Licence added')
      onSaved?.(saved.license.id)
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in blank) form.setError(field as keyof LicenseFormInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }

  return (
    <form
      onSubmit={form.handleSubmit(submit)}
      noValidate
      aria-label="Licence form"
      className="space-y-4"
    >
      {error ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}
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
      <div className="grid gap-4 sm:grid-cols-2">
        <FormInput
          label="Licence number"
          required
          maxLength={100}
          error={errors.license_no}
          {...form.register('license_no')}
        />
        <FormInput
          label="Issuing authority"
          maxLength={150}
          error={errors.authority}
          {...form.register('authority')}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormDatePicker
          label="Expiry date"
          required
          error={errors.expiry_date}
          {...form.register('expiry_date')}
        />
        <FormInput
          label="Renewal fee (AED)"
          required
          inputMode="decimal"
          autoComplete="off"
          error={errors.renewal_fee}
          {...form.register('renewal_fee')}
        />
      </div>
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
          description="Normally the expiry moves only through Mark as renewed. A manual change is kept in the history."
          error={errors.reason}
          {...form.register('reason')}
        />
      ) : null}
      <FormActions
        submitLabel={license ? 'Save changes' : 'Add licence'}
        isSubmitting={create.isPending || update.isPending}
        onCancel={onDone}
      />
    </form>
  )
}

export function LicenseDialog({
  open,
  onOpenChange,
  license,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  license?: License | null
  onSaved?: (id: string) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{license ? 'Edit trade licence' : 'Add trade licence'}</DialogTitle>
          <DialogDescription>
            The status is calculated from the expiry date; it cannot be typed.
          </DialogDescription>
        </DialogHeader>
        <LicenseForm license={license} onSaved={onSaved} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}
