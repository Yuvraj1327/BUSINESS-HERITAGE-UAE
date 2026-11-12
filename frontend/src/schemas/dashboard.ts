import { z } from 'zod'
import { dailyReportSchema } from '@/schemas/reports'

const money = z.string()
const nullableMoney = z.string().nullable()
const date = z.string()

export const collectionsSchema = z.object({
  cash_received: money,
  pos_amount: money,
  bank_transfer: money,
  link_payment: money,
  total_received: money,
})

export const totalsSchema = z.object({
  report_count: z.number(),
  total_sales: money,
  total_orders: z.number(),
  collections: collectionsSchema,
  not_yet_received: money,
  shop_expenses: money,
  shop_savings: money,
  shop_expenses_excl_savings: money,
})
export type Totals = z.infer<typeof totalsSchema>

export const missingBranchSchema = z.object({
  branch_id: z.string(),
  branch_name: z.string(),
  missing_count: z.number(),
  dates: z.array(date),
})

export const missingSchema = z.object({
  status: z.enum(['ok', 'not_configured', 'before_start']),
  reporting_start: date.nullable(),
  date_from: date.nullable(),
  date_to: date.nullable(),
  expected: z.number(),
  received: z.number(),
  missing_count: z.number(),
  branches: z.array(missingBranchSchema),
})
export type MissingReports = z.infer<typeof missingSchema>

export const headOfficeSchema = z.object({
  total: money,
  savings: money,
  excl_savings: money,
  count: z.number(),
})

export const headOfficeRowSchema = z.object({
  id: z.string(),
  expense_date: date,
  branch_id: z.string().nullable(),
  branch_name: z.string().nullable(),
  category: z.string(),
  amount: money,
  paid_from: z.string(),
  is_saving: z.boolean(),
  note: z.string().nullable(),
})

export const branchDateViewSchema = z.object({
  branch_id: z.string().nullable(),
  date_from: date,
  date_to: date,
  totals: totalsSchema,
  reports: z.array(dailyReportSchema),
  missing: missingSchema,
  head_office: headOfficeSchema.nullable(),
  head_office_rows: z.array(headOfficeRowSchema).nullable(),
  head_office_unallocated: headOfficeSchema.nullable(),
})
export type BranchDateView = z.infer<typeof branchDateViewSchema>

export const kpisSchema = z.object({
  total_sales: money,
  total_received: money,
  not_yet_received: money,
  shop_expenses_excl_savings: money,
  head_office_expenses_excl_savings: money,
  total_savings: money,
  sales_minus_expenses: money,
  total_orders: z.number(),
  cash_bank_balance: nullableMoney,
})

export const balanceSchema = z.object({
  status: z.enum(['ok', 'not_configured', 'before_start']),
  reporting_start: date.nullable(),
  balance_date: date.nullable(),
  cash_in_hand: nullableMoney,
  enbd: nullableMoney,
  adcb: nullableMoney,
  pos_pending: nullableMoney,
  total: nullableMoney,
})

export const alertSchema = z.object({
  key: z.string(),
  title: z.string(),
  count: z.number(),
  detail: z.string().nullable().optional(),
  severity: z.enum(['warning', 'danger', 'info']),
  href: z.string().nullable().optional(),
})

export const branchRowSchema = z.object({
  branch_id: z.string(),
  branch_name: z.string(),
  report_count: z.number(),
  total_sales: money,
  total_orders: z.number(),
  total_received: money,
  not_yet_received: money,
  shop_expenses_excl_savings: money,
  shop_savings: money,
  head_office_excl_savings: money,
  missing_count: z.number().nullable(),
})

export const dayRowSchema = z.object({
  date,
  report_count: z.number(),
  missing_count: z.number().nullable(),
  total_sales: money,
  total_orders: z.number(),
  total_received: money,
  not_yet_received: money,
  shop_expenses_excl_savings: money,
  head_office_expenses_excl_savings: money,
  total_savings: money,
  sales_minus_expenses: money,
})

export const ownerDashboardSchema = z.object({
  mode: z.enum(['day', 'month', 'range']),
  preset: z.string().nullable().optional(),
  date_from: date,
  date_to: date,
  today: date,
  kpis: kpisSchema,
  balances: balanceSchema,
  missing: missingSchema,
  alerts: z.array(alertSchema),
  branches: z.array(branchRowSchema),
  unallocated_head_office_excl_savings: money,
  days: z.array(dayRowSchema).nullable(),
})
export type OwnerDashboard = z.infer<typeof ownerDashboardSchema>
