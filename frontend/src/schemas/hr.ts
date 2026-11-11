import { z } from 'zod'
import { auditEntrySchema } from '@/schemas/finance'
import { aedAmountSchema, isoDateSchema } from '@/schemas/common'

/* ---------- API responses. Statuses, days and totals are calculated by the backend from real dates. ---------- */
const money = z.string()
const date = z.string()

export const EMPLOYMENT_STATUSES = ['Active', 'On Leave', 'Visa Cancelled'] as const
export type EmploymentStatus = (typeof EMPLOYMENT_STATUSES)[number]
export const expiryStatusSchema = z.enum([
  'expired',
  'urgent',
  'upcoming',
  'normal',
  'not_recorded',
  'cancelled',
])
export type ExpiryStatus = z.infer<typeof expiryStatusSchema>

export const leaveSchema = z.object({
  leave_start: date,
  limit_date: date,
  days_on_leave: z.number(),
  days_remaining: z.number(),
  state: z.enum([
    'not_on_leave',
    'on_leave',
    'approaching_limit',
    'limit_reached',
    'visa_cancelled',
  ]),
})
export type Leave = z.infer<typeof leaveSchema>

export const employeeSchema = z.object({
  id: z.string(),
  full_name: z.string(),
  branch_id: z.string(),
  branch_name: z.string(),
  role_title: z.string().nullable(),
  monthly_salary: money,
  status: z.enum(EMPLOYMENT_STATUSES),
  stored_status: z.enum(['Active', 'Leave']),
  leave: leaveSchema.nullable(),
  visa_cancelled: z.boolean(),
  visa_cancelled_date: date.nullable(),
  visa_expiry: date.nullable(),
  visa_status: expiryStatusSchema,
  visa_days_remaining: z.number().nullable(),
  passport_expiry: date.nullable(),
  passport_status: expiryStatusSchema,
  passport_days_remaining: z.number().nullable(),
  notes: z.string().nullable(),
  payroll_eligible: z.boolean(),
  archived: z.boolean(),
  archive_reason: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  created_by_name: z.string().nullable(),
  updated_by_name: z.string().nullable(),
})
export type Employee = z.infer<typeof employeeSchema>

export const employeePageSchema = z.object({
  items: z.array(employeeSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})
export const employeeDetailSchema = z.object({
  employee: employeeSchema,
  history: z.array(auditEntrySchema),
})
export type EmployeeDetail = z.infer<typeof employeeDetailSchema>

export const employeeSummarySchema = z.object({
  total_active: z.number(),
  on_leave: z.number(),
  close_to_limit: z.number(),
  visa_cancelled: z.number(),
  monthly_payroll: money,
  payroll_employees: z.number(),
})
export type EmployeeSummary = z.infer<typeof employeeSummarySchema>

export const leaveSummarySchema = z.object({
  on_leave: z.number(),
  approaching: z.number(),
  limit_reached: z.number(),
  visa_cancelled_by_leave: z.number(),
  items: z.array(employeeSchema),
})
export type LeaveSummary = z.infer<typeof leaveSummarySchema>

export const complianceRowSchema = z.object({
  employee_id: z.string(),
  employee_name: z.string(),
  branch_id: z.string(),
  branch_name: z.string(),
  employment_status: z.enum(EMPLOYMENT_STATUSES),
  expiry_date: date.nullable(),
  status: expiryStatusSchema,
  days_remaining: z.number().nullable(),
})
export type ComplianceRow = z.infer<typeof complianceRowSchema>
export const compliancePageSchema = z.object({
  items: z.array(complianceRowSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})

const buckets = z.object({
  expired: z.number(),
  urgent: z.number(),
  upcoming: z.number(),
  normal: z.number(),
  not_recorded: z.number(),
  cancelled: z.number(),
})
export const complianceSummarySchema = z.object({
  visas: buckets,
  passports: buckets,
  visas_expiring_30: z.number(),
  passports_expiring_30: z.number(),
  passports_under_6_months: z.number(),
  visas_cancelled: z.number(),
})
export type ComplianceSummary = z.infer<typeof complianceSummarySchema>

export const expiryChangeSchema = z.object({
  occurred_at: z.string(),
  actor_name: z.string().nullable(),
  old_expiry: date.nullable(),
  new_expiry: date.nullable(),
  reason: z.string().nullable(),
})
export type ExpiryChange = z.infer<typeof expiryChangeSchema>
export const expiryHistorySchema = z.object({
  visa: z.array(expiryChangeSchema),
  passport: z.array(expiryChangeSchema),
})

export const licenseSchema = z.object({
  id: z.string(),
  branch_id: z.string(),
  branch_name: z.string(),
  license_no: z.string(),
  authority: z.string().nullable(),
  expiry_date: date,
  renewal_fee: money,
  notes: z.string().nullable(),
  status: expiryStatusSchema,
  days_remaining: z.number(),
  renewal_count: z.number(),
  last_renewed_on: date.nullable(),
  archived: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  updated_by_name: z.string().nullable(),
})
export type License = z.infer<typeof licenseSchema>
export const licensePageSchema = z.object({
  items: z.array(licenseSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})
export const licenseSummarySchema = z.object({
  total: z.number(),
  expired: z.number(),
  expiring_30: z.number(),
  expiring_60: z.number(),
  renewal_fees_due: money,
  fees_due_count: z.number(),
})
export type LicenseSummary = z.infer<typeof licenseSummarySchema>
export const renewalSchema = z.object({
  id: z.string(),
  license_id: z.string(),
  renewed_on: date,
  previous_expiry: date,
  new_expiry: date,
  renewal_fee: money,
  note: z.string().nullable(),
  created_at: z.string(),
  created_by_name: z.string().nullable(),
})
export type Renewal = z.infer<typeof renewalSchema>
export const licenseDetailSchema = z.object({
  license: licenseSchema,
  renewals: z.array(renewalSchema),
  history: z.array(auditEntrySchema),
})
export type LicenseDetail = z.infer<typeof licenseDetailSchema>

export const complianceAlertSchema = z.object({
  key: z.string(),
  kind: z.string(),
  severity: z.enum(['danger', 'warning']),
  title: z.string(),
  detail: z.string(),
  due_date: date.nullable(),
  days_remaining: z.number().nullable(),
  href: z.string(),
})
export type ComplianceAlert = z.infer<typeof complianceAlertSchema>
export const alertFeedSchema = z.object({
  items: z.array(complianceAlertSchema),
  total: z.number(),
  danger: z.number(),
  warning: z.number(),
})

/* ---------- Forms: client-side mirrors of the server rules, for fast feedback only. The API validates again. ---------- */
const optionalText = (max: number) => z.string().trim().max(max, `At most ${max} characters`)
const optionalDate = z
  .string()
  .trim()
  .refine((v) => v === '' || isoDateSchema.safeParse(v).success, 'Use YYYY-MM-DD')
const salary = z.string().trim().min(1, 'Enter the monthly salary').pipe(aedAmountSchema)
export const reasonSchema = z
  .string()
  .trim()
  .min(3, 'Enter a reason (at least 3 characters)')
  .max(500)

export const employeeFormSchema = z.object({
  full_name: z.string().trim().min(1, 'Enter the employee name').max(150),
  branch_id: z.string().min(1, 'Choose a branch'),
  role_title: optionalText(100),
  monthly_salary: salary,
  passport_expiry: optionalDate,
  visa_expiry: optionalDate,
  notes: optionalText(1000),
  reason: optionalText(500),
})
export type EmployeeFormInput = z.input<typeof employeeFormSchema>
export type EmployeeFormValues = z.output<typeof employeeFormSchema>

export const licenseFormSchema = z.object({
  branch_id: z.string().min(1, 'Choose a branch'),
  license_no: z.string().trim().min(1, 'Enter the licence number').max(100),
  authority: optionalText(150),
  expiry_date: isoDateSchema,
  renewal_fee: z.string().trim().min(1, 'Enter the renewal fee').pipe(aedAmountSchema),
  notes: optionalText(1000),
  reason: optionalText(500),
})
export type LicenseFormInput = z.input<typeof licenseFormSchema>
export type LicenseFormValues = z.output<typeof licenseFormSchema>
