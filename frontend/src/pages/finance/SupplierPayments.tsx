import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useAddDue, useMarkPaid, useRecordPayment } from '@/hooks/use-finance'
import { toApiError } from '@/lib/errors'
import {
  PAY_ACCOUNTS,
  dueFormSchema,
  paymentFormSchema,
  type DueFormInput,
  type DueFormValues,
  type PayAccount,
  type PaymentFormInput,
  type PaymentFormValues,
  type Supplier,
} from '@/schemas/finance'
import { dubaiToday, formatAED } from '@/utils/format'

const sources = PAY_ACCOUNTS.map((a) => ({ value: a, label: a }))

function FormError({ message }: { message: string | null }) {
  return message ? (
    <p
      role="alert"
      className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
    >
      {message}
    </p>
  ) : null
}

interface Props {
  supplier: Supplier
  open: boolean
  onOpenChange: (open: boolean) => void
  minDate?: string
}

export function PaymentDialog({ supplier, open, onOpenChange, minDate }: Props) {
  const today = dubaiToday()
  const outstanding = Number(supplier.outstanding)
  const schema = useMemo(
    () => paymentFormSchema({ today, minDate, outstanding }),
    [today, minDate, outstanding],
  )
  const blank: PaymentFormInput = {
    payment_date: today,
    amount: '',
    paid_from: '' as 'Cash',
    reference: '',
    note: '',
  }
  const form = useForm<PaymentFormInput, unknown, PaymentFormValues>({
    resolver: zodResolver(schema),
    defaultValues: blank,
  })
  const record = useRecordPayment()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState

  async function submit(v: PaymentFormValues) {
    setError(null)
    try {
      await record.mutateAsync({
        id: supplier.id,
        body: {
          payment_date: v.payment_date,
          amount: v.amount,
          paid_from: v.paid_from,
          ...(v.reference ? { reference: v.reference } : {}),
          ...(v.note ? { note: v.note } : {}),
          client_key: key,
        },
      })
      toast.success('Payment recorded')
      setKey(crypto.randomUUID())
      form.reset(blank)
      onOpenChange(false)
    } catch (e) {
      const err = toApiError(e)
      setError(err.message)
      if (err.code === 'duplicate_transaction') setKey(crypto.randomUUID())
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record payment to {supplier.name}</DialogTitle>
          <DialogDescription>
            Outstanding now {formatAED(supplier.outstanding)}. A partial payment lowers it; the
            history is kept.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(submit)}
          noValidate
          aria-label="Payment form"
          className="space-y-4"
        >
          <FormError message={error} />
          <FormDatePicker
            label="Payment date"
            required
            min={minDate}
            max={today}
            error={errors.payment_date}
            {...form.register('payment_date')}
          />
          <FormInput
            label="Amount (AED)"
            required
            inputMode="decimal"
            autoComplete="off"
            error={errors.amount}
            {...form.register('amount')}
          />
          <Controller
            control={form.control}
            name="paid_from"
            render={({ field }) => (
              <FormSelect
                label="Paid from"
                required
                value={field.value || ''}
                onValueChange={field.onChange}
                options={sources}
                error={errors.paid_from}
              />
            )}
          />
          <FormInput label="Reference" error={errors.reference} {...form.register('reference')} />
          <FormInput label="Notes" error={errors.note} {...form.register('note')} />
          <FormActions
            submitLabel="Record payment"
            isSubmitting={record.isPending}
            onCancel={() => onOpenChange(false)}
          />
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function DueDialog({ supplier, open, onOpenChange, minDate }: Props) {
  const today = dubaiToday()
  const schema = useMemo(() => dueFormSchema({ today, minDate }), [today, minDate])
  const blank: DueFormInput = { entry_date: today, amount: '', reference: '', note: '' }
  const form = useForm<DueFormInput, unknown, DueFormValues>({
    resolver: zodResolver(schema),
    defaultValues: blank,
  })
  const add = useAddDue()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState

  async function submit(v: DueFormValues) {
    setError(null)
    try {
      await add.mutateAsync({
        id: supplier.id,
        body: {
          entry_date: v.entry_date,
          amount: v.amount,
          ...(v.reference ? { reference: v.reference } : {}),
          ...(v.note ? { note: v.note } : {}),
          client_key: key,
        },
      })
      toast.success('Due recorded')
      setKey(crypto.randomUUID())
      form.reset(blank)
      onOpenChange(false)
    } catch (e) {
      const err = toApiError(e)
      setError(err.message)
      if (err.code === 'duplicate_transaction') setKey(crypto.randomUUID())
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add new due for {supplier.name}</DialogTitle>
          <DialogDescription>
            Increases the outstanding amount. This is a plain amount owed, not an invoice.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(submit)}
          noValidate
          aria-label="New due form"
          className="space-y-4"
        >
          <FormError message={error} />
          <FormDatePicker
            label="Date"
            required
            min={minDate}
            max={today}
            error={errors.entry_date}
            {...form.register('entry_date')}
          />
          <FormInput
            label="Amount (AED)"
            required
            inputMode="decimal"
            autoComplete="off"
            error={errors.amount}
            {...form.register('amount')}
          />
          <FormInput label="Reference" error={errors.reference} {...form.register('reference')} />
          <FormInput label="Notes" error={errors.note} {...form.register('note')} />
          <FormActions
            submitLabel="Add due"
            isSubmitting={add.isPending}
            onCancel={() => onOpenChange(false)}
          />
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Mark as Paid: records ONE payment for the full outstanding amount (it does not overwrite anything). */
export function MarkPaidDialog({ supplier, open, onOpenChange }: Omit<Props, 'minDate'>) {
  const mark = useMarkPaid()
  const [source, setSource] = useState<PayAccount | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [key, setKey] = useState(() => crypto.randomUUID())

  async function confirm() {
    if (!source) {
      setError('Choose where the payment is made from')
      return
    }
    setError(null)
    try {
      await mark.mutateAsync({
        id: supplier.id,
        body: { payment_date: dubaiToday(), paid_from: source, client_key: key },
      })
      toast.success(`${supplier.name} marked as paid`)
      setKey(crypto.randomUUID())
      setSource('')
      onOpenChange(false)
    } catch (e) {
      const err = toApiError(e)
      setError(err.message)
      if (err.code === 'duplicate_transaction') setKey(crypto.randomUUID())
    }
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setError(null)
          setSource('')
        }
        onOpenChange(o)
      }}
      title={`Mark ${supplier.name} as paid?`}
      confirmLabel="Record full payment"
      isLoading={mark.isPending}
      onConfirm={confirm}
      description={
        <div className="space-y-3 text-left text-sm">
          <p>
            This records one payment of <strong>{formatAED(supplier.outstanding)}</strong> dated
            today. The outstanding amount drops to zero and the payment appears in the history.
          </p>
          <FormSelect
            label="Paid from"
            required
            value={source}
            onValueChange={(v) => setSource(v as PayAccount)}
            options={sources}
          />
          {error ? (
            <p role="alert" className="text-destructive">
              {error}
            </p>
          ) : null}
        </div>
      }
    />
  )
}
