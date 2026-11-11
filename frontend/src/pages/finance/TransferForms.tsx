import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useCreateSettlement, useCreateTransfer } from '@/hooks/use-finance'
import { toApiError } from '@/lib/errors'
import {
  PAY_ACCOUNTS,
  settlementFormSchema,
  transferFormSchema,
  type SettlementFormInput,
  type SettlementFormValues,
  type TransferFormInput,
  type TransferFormValues,
} from '@/schemas/finance'
import { dubaiToday } from '@/utils/format'

const accountOptions = PAY_ACCOUNTS.map((a) => ({ value: a, label: a }))
const bankOptions = [
  { value: 'ENBD', label: 'ENBD' },
  { value: 'ADCB', label: 'ADCB' },
]

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
  open: boolean
  onOpenChange: (open: boolean) => void
  /** First date money may move (the day after the opening balance date). */
  minDate?: string
}

export function TransferDialog({ open, onOpenChange, minDate }: Props) {
  const today = dubaiToday()
  const { branches } = useBranchContext()
  const schema = useMemo(() => transferFormSchema({ today, minDate }), [today, minDate])
  const blank: TransferFormInput = {
    transfer_date: today,
    from_account: '' as 'Cash',
    to_account: '' as 'ENBD',
    branch_id: '',
    amount: '',
    reference: '',
    note: '',
  }
  const form = useForm<TransferFormInput, unknown, TransferFormValues>({
    resolver: zodResolver(schema),
    defaultValues: blank,
  })
  const create = useCreateTransfer()
  const [key, setKey] = useState(() => crypto.randomUUID()) // one key per attempt: a double click cannot post twice
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState
  const from = useWatch({ control: form.control, name: 'from_account' })
  const to = useWatch({ control: form.control, name: 'to_account' })
  const needsBranch = from === 'Cash' || to === 'Cash'

  async function submit(v: TransferFormValues) {
    setError(null)
    try {
      await create.mutateAsync({
        transfer_date: v.transfer_date,
        from_account: v.from_account,
        to_account: v.to_account,
        ...(needsBranch ? { branch_id: v.branch_id } : {}),
        amount: v.amount,
        ...(v.reference ? { reference: v.reference } : {}),
        ...(v.note ? { note: v.note } : {}),
        client_key: key,
      })
      toast.success('Transfer recorded')
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
          <DialogTitle>New transfer</DialogTitle>
          <DialogDescription>
            Moves money between accounts as one debit and one matching credit. A transfer can never
            overdraw an account.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(submit)}
          noValidate
          aria-label="Transfer form"
          className="space-y-4"
        >
          <FormError message={error} />
          <FormDatePicker
            label="Date"
            required
            min={minDate}
            max={today}
            error={errors.transfer_date}
            {...form.register('transfer_date')}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Controller
              control={form.control}
              name="from_account"
              render={({ field }) => (
                <FormSelect
                  label="From"
                  required
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  options={accountOptions}
                  error={errors.from_account}
                />
              )}
            />
            <Controller
              control={form.control}
              name="to_account"
              render={({ field }) => (
                <FormSelect
                  label="To"
                  required
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  options={accountOptions}
                  error={errors.to_account}
                />
              )}
            />
          </div>
          {needsBranch ? (
            <Controller
              control={form.control}
              name="branch_id"
              render={({ field }) => (
                <FormSelect
                  label="Branch whose cash moves"
                  required
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  options={branches
                    .filter((b) => b.is_active)
                    .map((b) => ({ value: b.id, label: b.name }))}
                  placeholder="Select branch"
                  error={errors.branch_id}
                />
              )}
            />
          ) : null}
          <FormInput
            label="Amount (AED)"
            required
            inputMode="decimal"
            autoComplete="off"
            error={errors.amount}
            {...form.register('amount')}
          />
          <FormInput label="Reference" error={errors.reference} {...form.register('reference')} />
          <FormInput label="Note" error={errors.note} {...form.register('note')} />
          <FormActions
            submitLabel="Record transfer"
            isSubmitting={create.isPending}
            onCancel={() => onOpenChange(false)}
          />
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function SettlementDialog({ open, onOpenChange, minDate }: Props) {
  const today = dubaiToday()
  const schema = useMemo(() => settlementFormSchema({ today, minDate }), [today, minDate])
  const blank: SettlementFormInput = {
    settlement_date: today,
    bank: '' as 'ENBD',
    amount: '',
    reference: '',
    note: '',
  }
  const form = useForm<SettlementFormInput, unknown, SettlementFormValues>({
    resolver: zodResolver(schema),
    defaultValues: blank,
  })
  const create = useCreateSettlement()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState

  async function submit(v: SettlementFormValues) {
    setError(null)
    try {
      await create.mutateAsync({
        settlement_date: v.settlement_date,
        bank: v.bank,
        amount: v.amount,
        ...(v.reference ? { reference: v.reference } : {}),
        ...(v.note ? { note: v.note } : {}),
        client_key: key,
      })
      toast.success('POS settlement recorded')
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
          <DialogTitle>Record POS settlement</DialogTitle>
          <DialogDescription>
            When the card provider pays out, POS pending goes down and the receiving bank goes up by
            the same amount.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(submit)}
          noValidate
          aria-label="POS settlement form"
          className="space-y-4"
        >
          <FormError message={error} />
          <FormDatePicker
            label="Settlement date"
            required
            min={minDate}
            max={today}
            error={errors.settlement_date}
            {...form.register('settlement_date')}
          />
          <Controller
            control={form.control}
            name="bank"
            render={({ field }) => (
              <FormSelect
                label="Receiving bank"
                required
                value={field.value || ''}
                onValueChange={field.onChange}
                options={bankOptions}
                error={errors.bank}
              />
            )}
          />
          <FormInput
            label="Amount settled (AED)"
            required
            inputMode="decimal"
            autoComplete="off"
            error={errors.amount}
            {...form.register('amount')}
          />
          <FormInput label="Reference" error={errors.reference} {...form.register('reference')} />
          <FormInput label="Note" error={errors.note} {...form.register('note')} />
          <FormActions
            submitLabel="Record settlement"
            isSubmitting={create.isPending}
            onCancel={() => onOpenChange(false)}
          />
        </form>
      </DialogContent>
    </Dialog>
  )
}
