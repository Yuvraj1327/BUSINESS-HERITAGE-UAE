import { z } from 'zod'
import { catalogSchema, reportSchema } from '@/schemas/analytics'

/** Step 13 shapes. Money travels as decimal strings (never floats); the server is the only place amounts are computed. */
const money = z.union([z.string(), z.number()])

export const ORDER_STATUSES = [
  'New',
  'Scheduled',
  'Picked Up',
  'Processing',
  'Ready',
  'Out for Delivery',
  'Delivered',
  'Cancelled',
] as const
export const PAYMENT_STATUSES = ['Unpaid', 'Partial', 'Paid', 'Refunded'] as const
export const PAYMENT_METHODS = ['Cash', 'POS', 'Bank Transfer', 'Payment Link'] as const
export const SERVICE_TYPES = ['Standard', 'Express'] as const

export const orderRowSchema = z.object({
  id: z.string(),
  order_no: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  mobile: z.string(),
  area: z.string().nullable(),
  branch_id: z.string(),
  branch_name: z.string(),
  category: z.string(),
  service_type: z.string(),
  status: z.string(),
  payment_status: z.string(),
  order_date: z.string(),
  pickup_at: z.string().nullable(),
  pickup_address: z.string().nullable(),
  delivery_at: z.string(),
  delivery_address: z.string().nullable(),
  final_payable: money,
  amount_collected: money,
  outstanding: money,
  overdue: z.enum(['pickup', 'delivery']).nullable().optional(),
})
export type OrderRow = z.infer<typeof orderRowSchema>

export const orderPageSchema = z.object({
  items: z.array(orderRowSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})
export type OrderPage = z.infer<typeof orderPageSchema>

export const customerSchema = z.object({
  id: z.string(),
  branch_id: z.string(),
  branch_name: z.string(),
  name: z.string(),
  mobile: z.string(),
  whatsapp: z.string().nullable(),
  address: z.string().nullable(),
  area: z.string().nullable(),
  notes: z.string().nullable(),
  order_count: z.number(),
  total_billed: money,
  outstanding: money,
  last_order_date: z.string().nullable(),
  created_at: z.string(),
})
export type Customer = z.infer<typeof customerSchema>

export const customerPageSchema = z.object({
  items: z.array(customerSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})

export const paymentSchema = z.object({
  id: z.string(),
  payment_date: z.string(),
  amount: money,
  method: z.string(),
  reference: z.string().nullable(),
  note: z.string().nullable(),
  recorded_by: z.string().nullable(),
  created_at: z.string(),
})
export type OrderPayment = z.infer<typeof paymentSchema>

export const historySchema = z.object({
  id: z.number(),
  from_status: z.string().nullable(),
  to_status: z.string(),
  changed_by: z.string().nullable(),
  changed_at: z.string(),
  note: z.string().nullable(),
})
export type HistoryItem = z.infer<typeof historySchema>

export const orderDetailSchema = z.object({
  order: orderRowSchema,
  category_id: z.string(),
  notes: z.string().nullable(),
  order_total: money,
  discount: money,
  service_fee: money,
  cancel_reason: z.string().nullable(),
  cancelled_at: z.string().nullable(),
  delivered_at: z.string().nullable(),
  customer_whatsapp: z.string().nullable(),
  customer_address: z.string().nullable(),
  created_at: z.string(),
  created_by_name: z.string().nullable(),
  updated_at: z.string(),
  updated_by_name: z.string().nullable(),
  payments: z.array(paymentSchema),
  history: z.array(historySchema),
  next_status: z.string().nullable(),
  can_edit: z.boolean(),
  can_cancel: z.boolean(),
  can_pay: z.boolean(),
})
export type OrderDetail = z.infer<typeof orderDetailSchema>

export const balanceSchema = z.object({
  order_id: z.string(),
  final_payable: money,
  amount_collected: money,
  outstanding: money,
  payment_status: z.string(),
})
export type Balance = z.infer<typeof balanceSchema>

export const categorySchema = z.object({ id: z.string(), name: z.string(), is_active: z.boolean() })
export const categoriesSchema = z.array(categorySchema)
export type Category = z.infer<typeof categorySchema>

export const dashboardSchema = z.object({
  date: z.string(),
  kpis: z.object({
    total_orders: z.number(),
    todays_pickups: z.number(),
    todays_deliveries: z.number(),
    monthly_revenue: money,
    outstanding_payments: money,
  }),
  sections: z.array(
    z.object({
      key: z.string(),
      title: z.string(),
      count: z.number(),
      items: z.array(orderRowSchema),
    }),
  ),
})
export type OrderDashboard = z.infer<typeof dashboardSchema>

export const countsSchema = z.record(z.string(), z.number())

export const paymentSummarySchema = z.object({
  date_from: z.string(),
  date_to: z.string(),
  total: money,
  by_method: z.record(z.string(), money),
  payment_count: z.number(),
})

export { catalogSchema as orderReportCatalogSchema, reportSchema as orderReportSchema }

// ------------------------------------------------------------------ forms
const optionalText = (max: number) =>
  z
    .string()
    .max(max)
    .transform((v) => v.trim())

/** Accepts "12", "12.5", "12.50"; at most two decimals; never negative. Mirrors the server's MoneyIn. */
export const amountText = z
  .string()
  .trim()
  .regex(/^\d{1,10}(\.\d{1,2})?$/, 'Enter an amount such as 120 or 120.50')

export const customerFormSchema = z.object({
  name: z.string().trim().min(2, "Enter the customer's name").max(150),
  mobile: z
    .string()
    .trim()
    .min(5, 'Enter the mobile number')
    .max(30)
    .regex(/^[+\d][\d\s()-]{4,}$/, 'Use digits only, with an optional leading +'),
  whatsapp: optionalText(30),
  address: optionalText(500),
  area: optionalText(100),
  notes: optionalText(2000),
})
export type CustomerFormValues = z.infer<typeof customerFormSchema>
export type CustomerFormInput = z.input<typeof customerFormSchema>

export const orderFormSchema = z
  .object({
    category_id: z.string().min(1, 'Choose a service category'),
    service_type: z.enum(SERVICE_TYPES),
    notes: optionalText(2000),
    pickup_date: z.string(),
    pickup_time: z.string(),
    pickup_address: optionalText(500),
    delivery_date: z.string().min(1, 'Choose the expected delivery date'),
    delivery_time: z.string().min(1, 'Choose the expected delivery time'),
    delivery_address: optionalText(500),
    order_total: amountText,
    discount: amountText,
    service_fee: amountText,
  })
  .superRefine((v, ctx) => {
    if (Boolean(v.pickup_date) !== Boolean(v.pickup_time)) {
      ctx.addIssue({
        code: 'custom',
        path: [v.pickup_date ? 'pickup_time' : 'pickup_date'],
        message: 'Give both the pickup date and time, or leave both empty',
      })
    }
    if (
      v.pickup_date &&
      v.pickup_time &&
      v.delivery_date &&
      v.delivery_time &&
      `${v.delivery_date}T${v.delivery_time}` < `${v.pickup_date}T${v.pickup_time}`
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['delivery_date'],
        message: 'Expected delivery cannot be earlier than the pickup',
      })
    }
  })
export type OrderFormValues = z.infer<typeof orderFormSchema>
export type OrderFormInput = z.input<typeof orderFormSchema>

export const paymentFormSchema = z.object({
  amount: amountText,
  method: z.enum(PAYMENT_METHODS),
  payment_date: z.string().min(1, 'Choose the payment date'),
  reference: optionalText(100),
  note: optionalText(500),
})
export type PaymentFormValues = z.infer<typeof paymentFormSchema>
export type PaymentFormInput = z.input<typeof paymentFormSchema>

/** Client-side preview of the server formula: final payable = total - discount + service fee. Display only. */
export function previewFinalPayable(total: string, discount: string, fee: string): number | null {
  const ok = [total, discount, fee].every((v) => /^\d{1,10}(\.\d{1,2})?$/.test(v.trim()))
  if (!ok) return null
  const cents = (v: string) => Math.round(Number(v) * 100)
  return (cents(total) - cents(discount) + cents(fee)) / 100
}
