import { z } from 'zod'

/** Step 12 report shapes. Money travels as decimal strings; every report is the same columns + rows table. */
export const reportColumnSchema = z.object({
  key: z.string(),
  label: z.string(),
  kind: z.enum(['text', 'money', 'int', 'pct', 'date', 'datetime']),
})
export type ReportColumn = z.infer<typeof reportColumnSchema>

const appliedFiltersSchema = z.object({
  date_from: z.string(),
  date_to: z.string(),
  period: z.enum(['day', 'week', 'month', 'year']),
  branch_id: z.string().nullable(),
  branch_name: z.string(),
  supplier_id: z.string().nullable().optional(),
  account: z.string().nullable().optional(),
})

export const reportSchema = z.object({
  key: z.string(),
  title: z.string(),
  description: z.string(),
  filters: appliedFiltersSchema,
  columns: z.array(reportColumnSchema),
  rows: z.array(z.record(z.string(), z.unknown())),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  summary: z.array(
    z.object({
      label: z.string(),
      value: z.unknown(),
      kind: z.enum(['text', 'money', 'int', 'pct', 'date', 'datetime']),
    }),
  ),
  notes: z.array(z.string()),
  generated_at: z.string(),
})
export type Report = z.infer<typeof reportSchema>
export type ReportRow = Report['rows'][number]

export const catalogSchema = z.array(
  z.object({ key: z.string(), title: z.string(), category: z.string(), description: z.string() }),
)
export type CatalogItem = z.infer<typeof catalogSchema>[number]

const money = z.union([z.string(), z.number()])
export const overviewSchema = z.object({
  filters: appliedFiltersSchema,
  kpis: z.object({
    total_sales: money,
    total_collections: money,
    total_orders: z.number(),
    shop_expenses: money,
    head_office_expenses: money,
    total_savings: money,
    sales_minus_expenses: money,
    cash_bank_balance: money.nullable(),
    not_yet_received: money,
    balance_status: z.string(),
    balance_date: z.string().nullable(),
  }),
  notes: z.array(z.string()),
  generated_at: z.string(),
})
export type Overview = z.infer<typeof overviewSchema>

export const chartSetSchema = z.object({
  filters: appliedFiltersSchema,
  charts: z.array(
    z.object({
      key: z.string(),
      title: z.string(),
      kind: z.enum(['line', 'bar', 'pie']),
      unit: z.enum(['AED', 'count']),
      series: z.array(z.string()),
      points: z.array(z.object({ label: z.string(), values: z.record(z.string(), z.unknown()) })),
      empty_message: z.string(),
    }),
  ),
  generated_at: z.string(),
})
export type Chart = z.infer<typeof chartSetSchema>['charts'][number]

export const actorsSchema = z.array(z.object({ id: z.string(), name: z.string() }))
