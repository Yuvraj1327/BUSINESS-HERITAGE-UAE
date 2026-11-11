import { z } from 'zod'
import { aedAmountSchema, isoDateSchema } from '@/schemas/common'

/* ---------- API responses. The backend does all arithmetic; the UI only parses and displays. ---------- */
const money = z.string()
const nullableMoney = z.string().nullable()

export const BANKS = ['ENBD', 'ADCB'] as const
export const PAY_ACCOUNTS = ['Cash', 'ENBD', 'ADCB'] as const
export const LEDGER_ACCOUNTS = ['Cash', 'ENBD', 'ADCB', 'POS Pending'] as const
export type PayAccount = (typeof PAY_ACCOUNTS)[number]
export type LedgerAccountName = (typeof LEDGER_ACCOUNTS)[number]
const account = z.enum(PAY_ACCOUNTS)
const ledgerAccount = z.enum(LEDGER_ACCOUNTS)

export const auditEntrySchema = z.object({
  id: z.number(),
  occurred_at: z.string(),
  actor_name: z.string().nullable(),
  action: z.string(),
  table_name: z.string(),
  record_id: z.string().nullable(),
  reason: z.string().nullable(),
  old_values: z.record(z.string(), z.unknown()).nullable(),
  new_values: z.record(z.string(), z.unknown()).nullable(),
})
export type AuditEntry = z.infer<typeof auditEntrySchema>

export const openingBalancesSchema = z.object({
  status: z.enum(['not_configured', 'configured']),
  as_of_date: isoDateSchema.nullable(),
  tracking_start: isoDateSchema.nullable(),
  receipts_bank: z.enum(BANKS).nullable(),
  enbd_balance: money,
  adcb_balance: money,
  pos_pending: money,
  savings_brought_forward: money,
  branch_cash: z.array(z.object({ branch_id: z.string(), branch_name: z.string(), amount: money })),
  supplier_dues: z.array(
    z.object({ supplier_id: z.string(), supplier_name: z.string(), amount: money }),
  ),
  total_branch_cash: money,
  total_supplier_dues: money,
  date_locked: z.boolean(),
  updated_at: z.string().nullable(),
  updated_by_name: z.string().nullable(),
})
export type OpeningBalances = z.infer<typeof openingBalancesSchema>

export const balancesSchema = z.object({
  status: z.enum(['not_configured', 'ok']),
  tracking_start: isoDateSchema.nullable(),
  balance_date: isoDateSchema.nullable(),
  cash_in_hand: nullableMoney,
  enbd: nullableMoney,
  adcb: nullableMoney,
  pos_pending: nullableMoney,
  total_cash_bank: nullableMoney,
  total_savings: nullableMoney,
})
export type Balances = z.infer<typeof balancesSchema>

export const accountsReportSchema = z.object({
  status: z.enum(['not_configured', 'ok']),
  date_from: isoDateSchema,
  date_to: isoDateSchema,
  accounts: z.array(
    z.object({
      account: ledgerAccount,
      opening: money,
      incoming: money,
      outgoing: money,
      closing: money,
    }),
  ),
})
export type AccountsReport = z.infer<typeof accountsReportSchema>

export const branchCashReportSchema = z.object({
  status: z.enum(['not_configured', 'ok']),
  balance_date: isoDateSchema.nullable(),
  rows: z.array(
    z.object({
      branch_id: z.string().nullable(),
      branch_name: z.string(),
      opening: money,
      incoming: money,
      outgoing: money,
      closing: money,
    }),
  ),
  total: money,
})
export type BranchCashReport = z.infer<typeof branchCashReportSchema>

export const ledgerRowSchema = z.object({
  txn_date: isoDateSchema,
  txn_type: z.string(),
  source_table: z.string(),
  source_id: z.string(),
  branch_id: z.string().nullable(),
  branch_name: z.string().nullable(),
  account: ledgerAccount,
  amount: money,
  description: z.string().nullable(),
  created_by: z.string().nullable(),
  created_by_name: z.string().nullable(),
  created_at: z.string(),
})
export type LedgerRow = z.infer<typeof ledgerRowSchema>

export const ledgerPageSchema = z.object({
  status: z.enum(['not_configured', 'ok']),
  items: z.array(ledgerRowSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  total_incoming: money,
  total_outgoing: money,
})
export type LedgerPage = z.infer<typeof ledgerPageSchema>

export const transferSchema = z.object({
  id: z.string(),
  transfer_date: isoDateSchema,
  from_account: account,
  to_account: account,
  branch_id: z.string().nullable(),
  branch_name: z.string().nullable(),
  amount: money,
  reference: z.string().nullable(),
  note: z.string().nullable(),
  created_at: z.string(),
  voided: z.boolean(),
})
export type Transfer = z.infer<typeof transferSchema>

export const settlementSchema = z.object({
  id: z.string(),
  settlement_date: isoDateSchema,
  bank: z.enum(BANKS),
  amount: money,
  reference: z.string().nullable(),
  note: z.string().nullable(),
  created_at: z.string(),
  voided: z.boolean(),
})
export type Settlement = z.infer<typeof settlementSchema>

export const categorySchema = z.object({ id: z.string(), name: z.string() })
export type ExpenseCategory = z.infer<typeof categorySchema>

export const expenseSchema = z.object({
  id: z.string(),
  expense_date: isoDateSchema,
  branch_id: z.string().nullable(),
  branch_name: z.string().nullable(),
  category_id: z.string(),
  category: z.string(),
  amount: money,
  paid_from: account,
  note: z.string().nullable(),
  is_saving: z.boolean(),
  voided: z.boolean(),
  void_reason: z.string().nullable(),
  corrects_id: z.string().nullable(),
  created_at: z.string(),
  created_by_name: z.string().nullable(),
})
export type Expense = z.infer<typeof expenseSchema>

export const expensePageSchema = z.object({
  items: z.array(expenseSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  totals: z.object({ total: money, savings: money, excl_savings: money, count: z.number() }),
})
export type ExpensePage = z.infer<typeof expensePageSchema>

export const expenseDetailSchema = z.object({
  expense: expenseSchema,
  history: z.array(auditEntrySchema),
})
export type ExpenseDetail = z.infer<typeof expenseDetailSchema>

export const supplierSchema = z.object({
  id: z.string(),
  name: z.string(),
  category: z.string().nullable(),
  payment_terms: z.string().nullable(),
  notes: z.string().nullable(),
  is_active: z.boolean(),
  opening_outstanding: money,
  new_dues: money,
  total_paid: money,
  outstanding: money,
  created_at: z.string(),
})
export type Supplier = z.infer<typeof supplierSchema>

export const supplierPageSchema = z.object({
  items: z.array(supplierSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})
export type SupplierPage = z.infer<typeof supplierPageSchema>

export const supplierSummarySchema = z.object({
  total_suppliers: z.number(),
  total_outstanding: money,
  total_paid: money,
  with_outstanding: z.number(),
})
export type SupplierSummary = z.infer<typeof supplierSummarySchema>

export const supplierEntrySchema = z.object({
  id: z.string(),
  supplier_id: z.string(),
  supplier_name: z.string(),
  entry_date: isoDateSchema,
  kind: z.enum(['due', 'payment']),
  amount: money,
  paid_from: account.nullable(),
  branch_name: z.string().nullable(),
  reference: z.string().nullable(),
  note: z.string().nullable(),
  voided: z.boolean(),
  void_reason: z.string().nullable(),
  created_at: z.string(),
  created_by_name: z.string().nullable(),
})
export type SupplierEntry = z.infer<typeof supplierEntrySchema>

export const supplierEntryPageSchema = z.object({
  items: z.array(supplierEntrySchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})
export type SupplierEntryPage = z.infer<typeof supplierEntryPageSchema>

/* ---------- Forms: client-side mirrors of the server rules, for fast feedback only. The API validates again. ---------- */
const requiredAmount = (msg: string) => z.string().trim().min(1, msg).pipe(aedAmountSchema)
const optionalAmount = z
  .string()
  .trim()
  .transform((v) => (v === '' ? '0' : v))
  .pipe(aedAmountSchema)
const positiveAmount = (msg: string) =>
  requiredAmount(msg).refine((v) => Number(v) > 0, 'Amount must be greater than zero')
const optionalText = (max: number) => z.string().trim().max(max, `At most ${max} characters`)

export function expenseFormSchema(opts: { today: string; minDate?: string }) {
  return z.object({
    expense_date: isoDateSchema
      .refine((d) => d <= opts.today, 'Date cannot be in the future')
      .refine((d) => !opts.minDate || d >= opts.minDate, 'Date is before tracking starts'),
    branch_id: z.string(), // '' = All branches
    category_id: z.string().min(1, 'Choose a category'),
    amount: positiveAmount('Enter the amount'),
    paid_from: z.enum(PAY_ACCOUNTS, { message: 'Choose where it was paid from' }),
    note: optionalText(500),
    is_saving: z.boolean(),
  })
}
export type ExpenseFormInput = z.input<ReturnType<typeof expenseFormSchema>>
export type ExpenseFormValues = z.output<ReturnType<typeof expenseFormSchema>>

export const supplierFormSchema = z.object({
  name: z.string().trim().min(1, 'Enter the supplier name').max(150),
  category: optionalText(200),
  payment_terms: optionalText(200),
  notes: optionalText(1000),
  is_active: z.boolean(),
  opening_outstanding: optionalAmount,
})
export type SupplierFormInput = z.input<typeof supplierFormSchema>
export type SupplierFormValues = z.output<typeof supplierFormSchema>

export function paymentFormSchema(opts: { today: string; minDate?: string; outstanding: number }) {
  return z
    .object({
      payment_date: isoDateSchema
        .refine((d) => d <= opts.today, 'Date cannot be in the future')
        .refine((d) => !opts.minDate || d >= opts.minDate, 'Date is before tracking starts'),
      amount: positiveAmount('Enter the payment amount'),
      paid_from: z.enum(PAY_ACCOUNTS, { message: 'Choose where it was paid from' }),
      reference: optionalText(120),
      note: optionalText(500),
    })
    .refine((v) => Number(v.amount) <= opts.outstanding + 0.000001, {
      path: ['amount'],
      message: 'Payment cannot exceed the outstanding amount',
    })
}
export type PaymentFormInput = z.input<ReturnType<typeof paymentFormSchema>>
export type PaymentFormValues = z.output<ReturnType<typeof paymentFormSchema>>

export function transferFormSchema(opts: { today: string; minDate?: string }) {
  return z
    .object({
      transfer_date: isoDateSchema
        .refine((d) => d <= opts.today, 'Date cannot be in the future')
        .refine((d) => !opts.minDate || d >= opts.minDate, 'Date is before tracking starts'),
      from_account: z.enum(PAY_ACCOUNTS, { message: 'Choose the source account' }),
      to_account: z.enum(PAY_ACCOUNTS, { message: 'Choose the destination account' }),
      branch_id: z.string(),
      amount: positiveAmount('Enter the amount'),
      reference: optionalText(120),
      note: optionalText(500),
    })
    .superRefine((v, ctx) => {
      if (v.from_account === v.to_account)
        ctx.addIssue({
          code: 'custom',
          path: ['to_account'],
          message: 'Choose two different accounts',
        })
      const touchesCash = v.from_account === 'Cash' || v.to_account === 'Cash'
      if (touchesCash && !v.branch_id)
        ctx.addIssue({
          code: 'custom',
          path: ['branch_id'],
          message: 'Choose the branch whose cash moves',
        })
    })
}
export type TransferFormInput = z.input<ReturnType<typeof transferFormSchema>>
export type TransferFormValues = z.output<ReturnType<typeof transferFormSchema>>

export function settlementFormSchema(opts: { today: string; minDate?: string }) {
  return z.object({
    settlement_date: isoDateSchema
      .refine((d) => d <= opts.today, 'Date cannot be in the future')
      .refine((d) => !opts.minDate || d >= opts.minDate, 'Date is before tracking starts'),
    bank: z.enum(BANKS, { message: 'Choose the receiving bank' }),
    amount: positiveAmount('Enter the settled amount'),
    reference: optionalText(120),
    note: optionalText(500),
  })
}
export type SettlementFormInput = z.input<ReturnType<typeof settlementFormSchema>>
export type SettlementFormValues = z.output<ReturnType<typeof settlementFormSchema>>

/** Opening balances form: every amount required (0 allowed), every branch present exactly once. */
export const openingFormSchema = z.object({
  as_of_date: isoDateSchema,
  receipts_bank: z.enum(BANKS, { message: 'Choose the receiving bank' }),
  enbd_balance: optionalAmount,
  adcb_balance: optionalAmount,
  pos_pending: optionalAmount,
  savings_brought_forward: optionalAmount,
  branch_cash: z.array(z.object({ branch_id: z.string(), amount: optionalAmount })),
  supplier_dues: z.array(z.object({ supplier_id: z.string(), amount: optionalAmount })),
  reason: optionalText(500),
})
export type OpeningFormInput = z.input<typeof openingFormSchema>
export type OpeningFormValues = z.output<typeof openingFormSchema>

export const voidReasonSchema = z
  .string()
  .trim()
  .min(3, 'Enter a reason (at least 3 characters)')
  .max(500)

export function dueFormSchema(opts: { today: string; minDate?: string }) {
  return z.object({
    entry_date: isoDateSchema
      .refine((d) => d <= opts.today, 'Date cannot be in the future')
      .refine((d) => !opts.minDate || d >= opts.minDate, 'Date is before tracking starts'),
    amount: positiveAmount('Enter the amount'),
    reference: optionalText(120),
    note: optionalText(500),
  })
}
export type DueFormInput = z.input<ReturnType<typeof dueFormSchema>>
export type DueFormValues = z.output<ReturnType<typeof dueFormSchema>>
