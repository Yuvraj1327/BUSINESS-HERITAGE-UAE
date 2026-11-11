import { zodResolver } from '@hookform/resolvers/zod'
import { Ban, CheckCircle2, Pencil, Repeat } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { FormTextarea } from '@/components/forms/form-textarea'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  useBounceCheque,
  useClearCheque,
  useReplaceCheque,
  useUpdateCheque,
} from '@/hooks/use-rentals'
import { toApiError } from '@/lib/errors'
import {
  chequeEditSchema,
  RENTAL_BANKS,
  replaceFormSchema,
  type Cheque,
  type ChequeEditInput,
  type ReplaceFormInput,
} from '@/schemas/rentals'
import { formatAED, formatDate } from '@/utils/format'
import { ActionDialog } from '@/pages/hr/shared'
import { todayDubai } from './helpers'

const bankOptions = RENTAL_BANKS.map((b) => ({ value: b, label: b }))

function ReplaceForm({ cheque, onDone }: { cheque: Cheque; onDone: () => void }) {
  const replace = useReplaceCheque()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<ReplaceFormInput>({
    resolver: zodResolver(replaceFormSchema),
    defaultValues: { cheque_no: '', cheque_date: '', bank: '', notes: '', reason: '' },
  })
  const { errors } = form.formState
  async function submit(v: ReplaceFormInput) {
    setError(null)
    try {
      await replace.mutateAsync({
        id: cheque.id,
        body: {
          cheque_no: v.cheque_no,
          reason: v.reason,
          ...(v.cheque_date ? { cheque_date: v.cheque_date } : {}),
          ...(v.bank ? { bank: v.bank as 'ENBD' | 'ADCB' } : {}),
          ...(v.notes ? { notes: v.notes } : {}),
        },
      })
      toast.success('Replacement cheque added')
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in form.getValues())
          form.setError(field as keyof ReplaceFormInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }
  return (
    <form
      noValidate
      className="space-y-4"
      aria-label="Replacement cheque"
      onSubmit={form.handleSubmit(submit)}
    >
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <FormInput
        label="New cheque number"
        required
        maxLength={50}
        error={errors.cheque_no}
        {...form.register('cheque_no')}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormDatePicker
          label="New cheque date"
          description="Leave blank for today."
          error={errors.cheque_date}
          {...form.register('cheque_date')}
        />
        <Controller
          control={form.control}
          name="bank"
          render={({ field }) => (
            <FormSelect
              label="Bank"
              description={`Leave as is to keep ${cheque.bank}.`}
              value={field.value || ''}
              onValueChange={field.onChange}
              options={bankOptions}
              error={errors.bank}
            />
          )}
        />
      </div>
      <FormTextarea
        label="Notes"
        maxLength={500}
        error={errors.notes}
        {...form.register('notes')}
      />
      <FormTextarea
        label="Reason (kept in the audit history)"
        required
        maxLength={500}
        error={errors.reason}
        {...form.register('reason')}
      />
      <FormActions
        submitLabel="Add replacement cheque"
        isSubmitting={replace.isPending}
        onCancel={onDone}
      />
    </form>
  )
}

function EditForm({ cheque, onDone }: { cheque: Cheque; onDone: () => void }) {
  const update = useUpdateCheque()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<ChequeEditInput>({
    resolver: zodResolver(chequeEditSchema),
    defaultValues: {
      cheque_no: cheque.cheque_no,
      cheque_date: cheque.cheque_date,
      bank: cheque.bank,
      notes: cheque.notes ?? '',
      reason: '',
    },
  })
  const { errors } = form.formState
  async function submit(v: ChequeEditInput) {
    setError(null)
    try {
      await update.mutateAsync({
        id: cheque.id,
        body: {
          cheque_no: v.cheque_no,
          cheque_date: v.cheque_date,
          bank: v.bank,
          reason: v.reason,
          ...(v.notes ? { notes: v.notes } : {}),
        },
      })
      toast.success('Cheque updated')
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in form.getValues())
          form.setError(field as keyof ChequeEditInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }
  return (
    <form
      noValidate
      className="space-y-4"
      aria-label="Edit cheque"
      onSubmit={form.handleSubmit(submit)}
    >
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <FormInput
        label="Cheque number"
        required
        maxLength={50}
        error={errors.cheque_no}
        {...form.register('cheque_no')}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormDatePicker
          label="Cheque date"
          required
          error={errors.cheque_date}
          {...form.register('cheque_date')}
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
      <p className="text-xs text-muted-foreground">
        The amount ({formatAED(cheque.amount)}) cannot be changed here: the cheques must always add
        up to the annual rent.
      </p>
      <FormTextarea
        label="Notes"
        maxLength={500}
        error={errors.notes}
        {...form.register('notes')}
      />
      <FormTextarea
        label="Reason for the change"
        required
        maxLength={500}
        error={errors.reason}
        {...form.register('reason')}
      />
      <FormActions submitLabel="Save changes" isSubmitting={update.isPending} onCancel={onDone} />
    </form>
  )
}

type Which = 'clear' | 'bounce' | 'replace' | 'edit' | null

/** Row / page actions for one cheque. Cleared and Bounced cheques are final; only a bounced one can be replaced. */
export function ChequeActions({ cheque, compact = false }: { cheque: Cheque; compact?: boolean }) {
  const [which, setWhich] = useState<Which>(null)
  const clear = useClearCheque()
  const bounce = useBounceCheque()
  const close = () => setWhich(null)
  const size = compact ? 'sm' : 'default'
  const needsReplacement = cheque.status === 'Bounced' && !cheque.superseded
  if (cheque.status === 'Cleared' || (cheque.status === 'Bounced' && !needsReplacement)) return null
  return (
    <Can module="rentals_cheques" action="update">
      <span className="inline-flex flex-wrap gap-2">
        {cheque.status === 'Pending' ? (
          <>
            <Button size={size} onClick={() => setWhich('clear')}>
              <CheckCircle2 aria-hidden /> Mark Cleared
            </Button>
            <Button size={size} variant="outline" onClick={() => setWhich('bounce')}>
              <Ban aria-hidden /> Mark Bounced
            </Button>
            <Button size={size} variant="outline" onClick={() => setWhich('edit')}>
              <Pencil aria-hidden /> Edit
            </Button>
          </>
        ) : (
          <Button size={size} onClick={() => setWhich('replace')}>
            <Repeat aria-hidden /> Replace cheque
          </Button>
        )}
      </span>
      {which === 'clear' ? (
        <ActionDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Mark cheque ${cheque.cheque_no} as cleared?`}
          description={
            <>
              {cheque.bank} will be reduced by <strong>{formatAED(cheque.amount)}</strong> on the
              cheque date ({formatDate(cheque.cheque_date)}), once. The cheque date, number, amount
              and bank stay as they are. A cleared cheque cannot be changed or cleared again.
            </>
          }
          confirmLabel="Mark Cleared"
          dateLabel="Date cleared"
          dateRequired={false}
          dateMax={todayDubai()}
          dateHint="Leave blank for today (Dubai). The bank balance uses the cheque date, not this date."
          reasonLabel="Note (optional)"
          reasonRequired={false}
          onSubmit={async (v) => {
            await clear.mutateAsync({
              id: cheque.id,
              ...(v.date ? { cleared_date: v.date } : {}),
              ...(v.reason ? { note: v.reason } : {}),
            })
            toast.success('Cheque marked as cleared')
          }}
        />
      ) : null}
      {which === 'bounce' ? (
        <ActionDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Mark cheque ${cheque.cheque_no} as bounced?`}
          description={
            <>
              No bank deduction is made. The bounced record is kept for history, an alert appears
              under Needs Attention, and you can add a replacement cheque. A bounced cheque cannot
              be cleared later.
            </>
          }
          destructive
          confirmLabel="Mark Bounced"
          dateLabel="Date bounced"
          dateRequired={false}
          dateMax={todayDubai()}
          dateHint="Leave blank for today (Dubai)."
          onSubmit={async (v) => {
            await bounce.mutateAsync({
              id: cheque.id,
              reason: v.reason,
              ...(v.date ? { bounced_date: v.date } : {}),
            })
            toast.success('Cheque marked as bounced')
          }}
        />
      ) : null}
      <Dialog open={which === 'replace' || which === 'edit'} onOpenChange={(o) => !o && close()}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {which === 'replace'
                ? `Replace bounced cheque ${cheque.cheque_no}`
                : `Edit cheque ${cheque.cheque_no}`}
            </DialogTitle>
            <DialogDescription>
              {which === 'replace'
                ? `A new Pending cheque for ${formatAED(cheque.amount)} is linked to the same agreement. The bounced record stays.`
                : 'Only pending cheques can be edited. Every change is kept in the audit history.'}
            </DialogDescription>
          </DialogHeader>
          {which === 'replace' ? <ReplaceForm cheque={cheque} onDone={close} /> : null}
          {which === 'edit' ? <EditForm cheque={cheque} onDone={close} /> : null}
        </DialogContent>
      </Dialog>
    </Can>
  )
}
