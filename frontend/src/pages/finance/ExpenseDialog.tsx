import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
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
import { useCategories, useCorrectExpense, useCreateExpense } from '@/hooks/use-finance'
import { toApiError } from '@/lib/errors'
import {
  PAY_ACCOUNTS,
  expenseFormSchema,
  voidReasonSchema,
  type Expense,
  type ExpenseFormInput,
  type ExpenseFormValues,
} from '@/schemas/finance'
import { dubaiToday } from '@/utils/format'

const ALL_BRANCH = 'all'
const sources = PAY_ACCOUNTS.map((a) => ({ value: a, label: a }))

const blank = (date: string): ExpenseFormInput => ({
  expense_date: date,
  branch_id: ALL_BRANCH,
  category_id: '',
  amount: '',
  paid_from: '' as 'Cash',
  note: '',
  is_saving: false,
})

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** When set the dialog corrects this expense (the original is voided with a reason, a replacement is recorded). */
  expense?: Expense | null
  minDate?: string
}

const fromExpense = (e: Expense): ExpenseFormInput => ({
  expense_date: e.expense_date,
  branch_id: e.branch_id ?? ALL_BRANCH,
  category_id: e.category_id,
  amount: e.amount,
  paid_from: e.paid_from,
  note: e.note ?? '',
  is_saving: e.is_saving,
})

function ExpenseForm({
  expense,
  minDate,
  onDone,
}: {
  expense?: Expense | null
  minDate?: string
  onDone: () => void
}) {
  const today = dubaiToday()
  const { branches } = useBranchContext()
  const categories = useCategories()
  const schema = useMemo(() => expenseFormSchema({ today, minDate }), [today, minDate])
  const form = useForm<ExpenseFormInput, unknown, ExpenseFormValues>({
    resolver: zodResolver(schema),
    defaultValues: expense ? fromExpense(expense) : blank(today),
  })
  const create = useCreateExpense()
  const correct = useCorrectExpense()
  const [key, setKey] = useState(() => crypto.randomUUID()) // protects against a double submit creating two expenses
  const [error, setError] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const { errors } = form.formState
  const editing = Boolean(expense)

  async function submit(v: ExpenseFormValues) {
    setError(null)
    const body = {
      expense_date: v.expense_date,
      ...(v.branch_id !== ALL_BRANCH ? { branch_id: v.branch_id } : {}),
      category_id: v.category_id,
      amount: v.amount,
      paid_from: v.paid_from,
      ...(v.note ? { note: v.note } : {}),
      is_saving: v.is_saving,
    }
    try {
      if (expense) {
        const parsed = voidReasonSchema.safeParse(reason)
        if (!parsed.success) {
          setReasonError(parsed.error.issues[0]?.message ?? 'Enter a reason')
          return
        }
        await correct.mutateAsync({ id: expense.id, body: { ...body, reason: parsed.data } })
        toast.success('Expense corrected')
      } else {
        await create.mutateAsync({ ...body, client_key: key })
        toast.success(v.is_saving ? 'Saving recorded' : 'Expense recorded')
        setKey(crypto.randomUUID())
      }
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in blank('')) form.setError(field as keyof ExpenseFormInput, { message: msgs[0] })
      }
      setError(err.message)
      if (err.code === 'duplicate_transaction') setKey(crypto.randomUUID())
    }
  }
  return (
    <form
      onSubmit={form.handleSubmit(submit)}
      noValidate
      aria-label="Expense form"
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
      <FormDatePicker
        label="Date"
        required
        min={minDate}
        max={today}
        error={errors.expense_date}
        {...form.register('expense_date')}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Controller
          control={form.control}
          name="branch_id"
          render={({ field }) => (
            <FormSelect
              label="Branch"
              value={field.value}
              onValueChange={field.onChange}
              options={[
                { value: ALL_BRANCH, label: 'All branches' },
                ...branches.filter((b) => b.is_active).map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
          )}
        />
        <Controller
          control={form.control}
          name="category_id"
          render={({ field }) => (
            <FormSelect
              label="Category"
              required
              value={field.value || ''}
              onValueChange={field.onChange}
              options={(categories.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
              placeholder={categories.isLoading ? 'Loading…' : 'Select category'}
              error={errors.category_id}
            />
          )}
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
      </div>
      <FormTextarea label="Note" maxLength={500} error={errors.note} {...form.register('note')} />
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-primary"
          {...form.register('is_saving')}
        />
        <span>
          <span className="font-medium">This is a saving</span>
          <span className="block text-muted-foreground">
            Counts towards Total Savings and is excluded from normal expenses. The money still
            leaves the account it was paid from.
          </span>
        </span>
      </label>
      {editing ? (
        <FormTextarea
          label="Reason for the correction"
          required
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={reasonError ?? undefined}
        />
      ) : null}
      <FormActions
        submitLabel={editing ? 'Save correction' : 'Record expense'}
        isSubmitting={create.isPending || correct.isPending}
        onCancel={onDone}
      />
    </form>
  )
}

export function ExpenseDialog({ open, onOpenChange, expense, minDate }: Props) {
  const editing = Boolean(expense)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editing ? 'Correct expense' : 'New head office expense'}</DialogTitle>
          <DialogDescription>
            {editing
              ? 'The original is voided with your reason and a corrected entry replaces it. Both stay in the audit trail.'
              : 'Shop expenses are entered in the Daily Report; use this form for head office payments only.'}
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so every opening starts from clean form state. */}
        <ExpenseForm expense={expense} minDate={minDate} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}
