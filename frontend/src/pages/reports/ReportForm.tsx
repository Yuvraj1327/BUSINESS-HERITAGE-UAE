import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { StatusBadge } from '@/components/common/status-badge'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { ALL_BRANCHES, useBranchContext } from '@/components/layout/branch-context'
import { useCreateDailyReport } from '@/hooks/use-reports'
import { toApiError } from '@/lib/errors'
import {
  reportFormSchema,
  type DailyReport,
  type ReportFormInput,
  type ReportFormValues,
} from '@/schemas/reports'
import type { ReportPayload } from '@/services/reports.service'
import { dubaiToday, formatAED, formatDate } from '@/utils/format'

const AMOUNT_FIELDS = [
  ['cash_received', 'Cash'],
  ['pos_amount', 'POS'],
  ['bank_transfer', 'Bank Transfers'],
  ['link_payment', 'Payment Links'],
  ['shop_expenses', 'Shop Expenses'],
  ['shop_savings', 'Savings'],
] as const

type FieldName = keyof ReportFormInput

const blank = (date: string, branch: string): ReportFormInput => ({
  report_date: date,
  branch_id: branch,
  total_sales: '',
  order_count: '',
  cash_received: '',
  pos_amount: '',
  bank_transfer: '',
  link_payment: '',
  shop_expenses: '',
  shop_savings: '',
})

export function ReportForm({ onSubmitted }: { onSubmitted: (r: DailyReport) => void }) {
  const { canChoose, selectedBranchId, selectedBranchName, branches } = useBranchContext()
  const today = dubaiToday()
  const schema = useMemo(
    () => reportFormSchema({ needsBranch: canChoose, today }),
    [canChoose, today],
  )
  const defaultBranch = canChoose && selectedBranchId !== ALL_BRANCHES ? selectedBranchId : ''
  const form = useForm<ReportFormInput, unknown, ReportFormValues>({
    resolver: zodResolver(schema),
    defaultValues: blank(today, defaultBranch),
  })
  const create = useCreateDailyReport()
  const [pending, setPending] = useState<ReportFormValues | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const { errors } = form.formState

  const branchName = (id: string) =>
    branches.find((b) => b.id === id)?.name ?? selectedBranchName ?? '—'

  async function send(values: ReportFormValues) {
    setFormError(null)
    const payload: ReportPayload = {
      report_date: values.report_date,
      // A Branch User never sends a branch: the server uses the one on their profile.
      ...(canChoose ? { branch_id: values.branch_id } : {}),
      total_sales: values.total_sales,
      order_count: Number(values.order_count),
      cash_received: values.cash_received,
      pos_amount: values.pos_amount,
      bank_transfer: values.bank_transfer,
      link_payment: values.link_payment,
      shop_expenses: values.shop_expenses,
      shop_savings: values.shop_savings,
    }
    try {
      const report = await create.mutateAsync(payload)
      setPending(null)
      toast.success('Daily report submitted')
      onSubmitted(report)
      form.reset(blank(today, canChoose ? values.branch_id : ''))
    } catch (e) {
      setPending(null)
      const err = toApiError(e)
      let mapped = false
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in blank('', '')) {
          form.setError(field as FieldName, { message: msgs[0] })
          mapped = true
        }
      }
      if (!mapped || err.code === 'duplicate_report') setFormError(err.message)
      toast.error(err.message)
    }
  }

  const draft = pending
  const received = draft
    ? ['cash_received', 'pos_amount', 'bank_transfer', 'link_payment'].reduce(
        (sum, k) => sum + Number(draft[k as keyof ReportFormValues]),
        0,
      )
    : 0

  return (
    <form
      onSubmit={form.handleSubmit((v) => setPending(v))}
      noValidate
      className="space-y-5"
      aria-label="Daily report form"
    >
      {formError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {formError}
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <FormDatePicker
          label="Report Date"
          required
          max={today}
          error={errors.report_date}
          {...form.register('report_date')}
        />
        {canChoose ? (
          <Controller
            control={form.control}
            name="branch_id"
            render={({ field }) => (
              <FormSelect
                label="Branch"
                required
                value={field.value || undefined}
                onValueChange={field.onChange}
                options={branches
                  .filter((b) => b.is_active)
                  .map((b) => ({ value: b.id, label: b.name }))}
                placeholder="Select branch"
                error={errors.branch_id}
              />
            )}
          />
        ) : (
          <div className="grid gap-1.5">
            <p className="text-sm leading-none font-medium">Branch</p>
            <p
              className="flex h-9 items-center rounded-md border bg-muted px-3 text-sm"
              data-testid="fixed-branch"
            >
              {selectedBranchName ?? '—'}
            </p>
            <p className="text-xs text-muted-foreground">Your assigned branch</p>
          </div>
        )}
        <FormInput
          label="Total Sales (AED)"
          required
          inputMode="decimal"
          autoComplete="off"
          error={errors.total_sales}
          {...form.register('total_sales')}
        />
        <FormInput
          label="Number of Orders"
          required
          inputMode="numeric"
          autoComplete="off"
          error={errors.order_count}
          {...form.register('order_count')}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {AMOUNT_FIELDS.map(([name, label]) => (
          <FormInput
            key={name}
            label={`${label} (AED)`}
            inputMode="decimal"
            autoComplete="off"
            placeholder="0.00"
            error={errors[name]}
            {...form.register(name)}
          />
        ))}
      </div>

      <FormActions
        submitLabel="Review & submit"
        isSubmitting={create.isPending}
        onCancel={() => {
          form.reset(blank(today, defaultBranch))
          setFormError(null)
        }}
        cancelLabel="Clear"
      />

      <ConfirmDialog
        open={draft !== null}
        onOpenChange={(open) => !open && setPending(null)}
        title="Submit this daily report?"
        confirmLabel="Submit report"
        isLoading={create.isPending}
        onConfirm={async () => {
          if (draft) await send(draft)
        }}
        description={
          draft ? (
            <div className="space-y-3 text-left text-sm">
              <p>
                A submitted report cannot be edited or deleted by branch users. Please check the
                figures.
              </p>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                <dt className="text-muted-foreground">Branch</dt>
                <dd className="font-medium">
                  {canChoose ? branchName(draft.branch_id) : (selectedBranchName ?? '—')}
                </dd>
                <dt className="text-muted-foreground">Date</dt>
                <dd className="font-medium">{formatDate(draft.report_date)}</dd>
                <dt className="text-muted-foreground">Total Sales</dt>
                <dd className="font-medium">{formatAED(draft.total_sales)}</dd>
                <dt className="text-muted-foreground">Collections entered</dt>
                <dd className="font-medium">{formatAED(received)}</dd>
                <dt className="text-muted-foreground">Shop Expenses / Savings</dt>
                <dd className="font-medium">
                  {formatAED(draft.shop_expenses)} / {formatAED(draft.shop_savings)}
                </dd>
              </dl>
            </div>
          ) : null
        }
      />
    </form>
  )
}

/** Shown after a successful submission: the totals come from the server response, not from this page. */
export function SubmittedSummary({ report }: { report: DailyReport }) {
  return (
    <div
      role="status"
      className="space-y-2 rounded-xl border border-success/40 bg-green-50 p-4 text-sm"
      data-testid="submitted-summary"
    >
      <p className="font-semibold text-success">
        Report submitted for {report.branch_name} on {formatDate(report.report_date)}
      </p>
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Total Collections</dt>
          <dd className="tabular font-semibold">{formatAED(report.total_received)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Difference (not yet received)</dt>
          <dd className="tabular flex items-center gap-2 font-semibold">
            {formatAED(report.difference)}
            <StatusBadge status={report.check === 'Matches' ? 'success' : 'warning'}>
              {report.check}
            </StatusBadge>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Shop Expenses excl. Savings</dt>
          <dd className="tabular font-semibold">{formatAED(report.shop_expenses_excl_savings)}</dd>
        </div>
      </dl>
    </div>
  )
}
