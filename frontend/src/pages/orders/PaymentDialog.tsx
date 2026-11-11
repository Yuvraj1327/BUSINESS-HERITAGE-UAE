import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useAddPayment } from '@/hooks/use-orders'
import { getErrorMessage } from '@/lib/errors'
import { PAYMENT_METHODS, paymentFormSchema, type PaymentFormInput } from '@/schemas/orders'
import { dubaiToday } from '@/utils/format'
import { aed } from './order-format'

/** Record one payment. Each payment is independent; overpayment is refused by the server and shown here. */
export function PaymentDialog({
  orderId,
  open,
  onOpenChange,
  outstanding,
}: {
  orderId: string
  open: boolean
  onOpenChange: (o: boolean) => void
  outstanding: string | number
}) {
  const add = useAddPayment(orderId)
  const [clientKey, setClientKey] = useState(() => crypto.randomUUID())
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PaymentFormInput>({
    resolver: zodResolver(paymentFormSchema) as never,
    defaultValues: {
      amount: '',
      method: 'Cash',
      payment_date: dubaiToday(),
      reference: '',
      note: '',
    },
  })

  async function submit(raw: PaymentFormInput) {
    setError(null)
    const v = paymentFormSchema.parse(raw)
    try {
      await add.mutateAsync({
        amount: v.amount,
        method: v.method,
        payment_date: v.payment_date,
        reference: v.reference || null,
        note: v.note || null,
        client_key: clientKey,
      })
      toast.success('Payment recorded')
      reset()
      setClientKey(crypto.randomUUID())
      onOpenChange(false)
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={(e) => void handleSubmit(submit)(e)} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>Record payment</DialogTitle>
            <DialogDescription>
              Outstanding now: {aed(outstanding)}. You cannot collect more than this.
            </DialogDescription>
          </DialogHeader>
          <FormInput
            label="Amount (AED)"
            required
            inputMode="decimal"
            error={errors.amount}
            {...register('amount')}
          />
          <Controller
            control={control}
            name="method"
            render={({ field }) => (
              <FormSelect
                label="Payment method"
                required
                value={field.value}
                onValueChange={field.onChange}
                options={PAYMENT_METHODS.map((m) => ({ value: m, label: m }))}
              />
            )}
          />
          <FormDatePicker
            label="Payment date"
            required
            max={dubaiToday()}
            error={errors.payment_date}
            {...register('payment_date')}
          />
          <FormInput
            label="Reference"
            maxLength={100}
            error={errors.reference}
            {...register('reference')}
          />
          <FormInput label="Note" maxLength={500} error={errors.note} {...register('note')} />
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={add.isPending}>
              Save payment
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
