import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { FormActions } from '@/components/forms/form-actions'
import { FormInput } from '@/components/forms/form-input'
import { FormTextarea } from '@/components/forms/form-textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useCreateSupplier, useUpdateSupplier } from '@/hooks/use-finance'
import { toApiError } from '@/lib/errors'
import {
  supplierFormSchema,
  type Supplier,
  type SupplierFormInput,
  type SupplierFormValues,
} from '@/schemas/finance'

const blank: SupplierFormInput = {
  name: '',
  category: '',
  payment_terms: '',
  notes: '',
  is_active: true,
  opening_outstanding: '',
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  supplier?: Supplier | null
  /** Opening dues can only be typed here before the Opening Balances are saved; after that they live there. */
  openingEditable: boolean
  onSaved?: (s: Supplier) => void
}

function SupplierForm({
  supplier,
  openingEditable,
  onSaved,
  onDone,
}: {
  supplier?: Supplier | null
  openingEditable: boolean
  onSaved?: (s: Supplier) => void
  onDone: () => void
}) {
  const form = useForm<SupplierFormInput, unknown, SupplierFormValues>({
    resolver: zodResolver(supplierFormSchema),
    defaultValues: supplier
      ? {
          name: supplier.name,
          category: supplier.category ?? '',
          payment_terms: supplier.payment_terms ?? '',
          notes: supplier.notes ?? '',
          is_active: supplier.is_active,
          opening_outstanding: '',
        }
      : blank,
  })
  const create = useCreateSupplier()
  const update = useUpdateSupplier()
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState

  async function submit(v: SupplierFormValues) {
    setError(null)
    const base = {
      name: v.name,
      ...(v.category ? { category: v.category } : {}),
      ...(v.payment_terms ? { payment_terms: v.payment_terms } : {}),
      ...(v.notes ? { notes: v.notes } : {}),
      is_active: v.is_active,
    }
    try {
      const saved = supplier
        ? await update.mutateAsync({ id: supplier.id, body: base })
        : await create.mutateAsync({
            ...base,
            ...(openingEditable && Number(v.opening_outstanding) > 0
              ? { opening_outstanding: v.opening_outstanding }
              : {}),
          })
      toast.success(supplier ? 'Supplier updated' : 'Supplier added')
      onSaved?.(saved)
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in blank) form.setError(field as keyof SupplierFormInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }
  return (
    <form
      onSubmit={form.handleSubmit(submit)}
      noValidate
      aria-label="Supplier form"
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
      <FormInput
        label="Supplier name"
        required
        maxLength={150}
        error={errors.name}
        {...form.register('name')}
      />
      <FormInput
        label="Supplies / service description"
        maxLength={200}
        error={errors.category}
        {...form.register('category')}
      />
      <FormInput
        label="Payment terms"
        maxLength={200}
        placeholder="e.g. 30 days"
        error={errors.payment_terms}
        {...form.register('payment_terms')}
      />
      {!supplier && openingEditable ? (
        <FormInput
          label="Opening outstanding (AED)"
          inputMode="decimal"
          autoComplete="off"
          description="What you owed this supplier before tracking started."
          error={errors.opening_outstanding}
          {...form.register('opening_outstanding')}
        />
      ) : null}
      <FormTextarea
        label="Notes"
        maxLength={1000}
        error={errors.notes}
        {...form.register('notes')}
      />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-primary" {...form.register('is_active')} />
        Active supplier
      </label>
      <FormActions
        submitLabel={supplier ? 'Save changes' : 'Add supplier'}
        isSubmitting={create.isPending || update.isPending}
        onCancel={onDone}
      />
    </form>
  )
}

export function SupplierDialog({ open, onOpenChange, supplier, openingEditable, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{supplier ? 'Edit supplier' : 'Add supplier'}</DialogTitle>
          <DialogDescription>
            Outstanding amounts are calculated from dues and payments; they cannot be typed over.
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so every opening starts from clean form state. */}
        <SupplierForm
          supplier={supplier}
          openingEditable={openingEditable}
          onSaved={onSaved}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}
