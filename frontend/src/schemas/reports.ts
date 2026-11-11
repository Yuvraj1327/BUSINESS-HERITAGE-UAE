import { z } from 'zod'
import { aedAmountSchema, isoDateSchema } from '@/schemas/common'

/* ---------- API responses (the backend does all arithmetic; these are only parsed and displayed) ---------- */
const money = z.string()

export const dailyReportSchema = z.object({
  id: z.string(),
  report_date: isoDateSchema,
  branch_id: z.string(),
  branch_name: z.string(),
  total_sales: money,
  order_count: z.number(),
  cash_received: money,
  pos_amount: money,
  bank_transfer: money,
  link_payment: money,
  shop_expenses: money,
  shop_savings: money,
  total_received: money,
  difference: money,
  check: z.enum(['Matches', 'Diff']),
  shop_expenses_excl_savings: money,
  created_at: z.string(),
})
export type DailyReport = z.infer<typeof dailyReportSchema>

export const dailyReportPageSchema = z.object({
  items: z.array(dailyReportSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})
export type DailyReportPage = z.infer<typeof dailyReportPageSchema>

/* ---------- Form ---------- */
const optionalAmount = z
  .string()
  .trim()
  .transform((v) => (v === '' ? '0' : v))
  .pipe(aedAmountSchema)

/**
 * Client-side mirror of the server rules, for fast feedback only. The API validates everything again and its
 * messages are shown too (field errors are mapped back onto the form).
 */
export function reportFormSchema(opts: { needsBranch: boolean; today: string }) {
  return z
    .object({
      report_date: isoDateSchema.refine(
        (d) => d <= opts.today,
        'Report date cannot be in the future',
      ),
      branch_id: z.string(),
      total_sales: z.string().trim().min(1, 'Enter the total sales').pipe(aedAmountSchema),
      order_count: z
        .string()
        .trim()
        .min(1, 'Enter the number of orders')
        .regex(/^\d{1,7}$/, 'Enter a whole number of orders (0 or more)'),
      cash_received: optionalAmount,
      pos_amount: optionalAmount,
      bank_transfer: optionalAmount,
      link_payment: optionalAmount,
      shop_expenses: optionalAmount,
      shop_savings: optionalAmount,
    })
    .superRefine((v, ctx) => {
      if (opts.needsBranch && !v.branch_id) {
        ctx.addIssue({ code: 'custom', path: ['branch_id'], message: 'Select a branch' })
      }
      if (Number(v.total_sales) <= 0) {
        ctx.addIssue({
          code: 'custom',
          path: ['total_sales'],
          message: 'Total sales must be greater than zero',
        })
      }
      if (Number(v.shop_savings) > Number(v.shop_expenses)) {
        ctx.addIssue({
          code: 'custom',
          path: ['shop_savings'],
          message: 'Savings cannot exceed shop expenses',
        })
      }
    })
}
export type ReportFormInput = z.input<ReturnType<typeof reportFormSchema>>
export type ReportFormValues = z.output<ReturnType<typeof reportFormSchema>>
