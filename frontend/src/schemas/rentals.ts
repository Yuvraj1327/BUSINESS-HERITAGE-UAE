import { z } from 'zod'
import { auditEntrySchema } from '@/schemas/finance'
import { aedAmountSchema, isoDateSchema } from '@/schemas/common'

/* ---------- API responses. Statuses, days, schedules and totals are calculated by the backend. ---------- */
const money = z.string()
const date = z.string()

export const RENTAL_BANKS = ['ENBD', 'ADCB'] as const
export type RentalBank = (typeof RENTAL_BANKS)[number]
export const bankSchema = z.enum(RENTAL_BANKS)
export const CHEQUE_STATUSES = ['Pending', 'Cleared', 'Bounced'] as const
export type ChequeStatus = (typeof CHEQUE_STATUSES)[number]
export const AGREEMENT_STATUSES = [
  'Scheduled',
  'Active',
  'Expiring',
  'Expired',
  'Renewed',
  'Terminated',
] as const
export type AgreementStatus = (typeof AGREEMENT_STATUSES)[number]
export const timingSchema = z.enum(['overdue', 'due_7', 'due_30', 'later', 'done'])
export type Timing = z.infer<typeof timingSchema>

export const chequeSchema = z.object({
  id: z.string(),
  agreement_id: z.string(),
  branch_id: z.string(),
  branch_name: z.string(),
  landlord: z.string(),
  unit: z.string().nullable(),
  cheque_no: z.string(),
  cheque_date: date,
  amount: money,
  bank: bankSchema,
  status: z.enum(CHEQUE_STATUSES),
  cleared_on: date.nullable(),
  bounced_on: date.nullable(),
  notes: z.string().nullable(),
  replaces_id: z.string().nullable(),
  replaces_no: z.string().nullable(),
  replaced_by_id: z.string().nullable(),
  replaced_by_no: z.string().nullable(),
  superseded: z.boolean(),
  timing: timingSchema,
  days_to_due: z.number().nullable(),
  affects_balance: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  cleared_by_name: z.string().nullable(),
  bounced_by_name: z.string().nullable(),
})
export type Cheque = z.infer<typeof chequeSchema>

export const chequePageSchema = z.object({
  items: z.array(chequeSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})

export const chequeSummarySchema = z.object({
  pending_count: z.number(),
  due_30_count: z.number(),
  overdue_count: z.number(),
  cleared_count: z.number(),
  bounced_count: z.number(),
  pending_amount: money,
  bounced_amount: money,
  bounced_unresolved_count: z.number(),
  bounced_unresolved_amount: money,
  next_cheque: chequeSchema.nullable(),
})
export type ChequeSummary = z.infer<typeof chequeSummarySchema>

export const agreementSchema = z.object({
  id: z.string(),
  branch_id: z.string(),
  branch_name: z.string(),
  landlord: z.string(),
  unit: z.string().nullable(),
  start_date: date,
  end_date: date,
  annual_rent: money,
  bank: bankSchema.nullable(),
  cheque_count: z.number().nullable(),
  first_cheque_date: date.nullable(),
  first_cheque_no: z.string().nullable(),
  notes: z.string().nullable(),
  stored_status: z.string(),
  status: z.enum(AGREEMENT_STATUSES),
  days_to_end: z.number(),
  renewed_from_id: z.string().nullable(),
  renewed_to_id: z.string().nullable(),
  live_cheques: z.number(),
  schedule_total: money,
  pending_count: z.number(),
  cleared_count: z.number(),
  bounced_count: z.number(),
  next_cheque_date: date.nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  created_by_name: z.string().nullable(),
  updated_by_name: z.string().nullable(),
})
export type Agreement = z.infer<typeof agreementSchema>

export const agreementPageSchema = z.object({
  items: z.array(agreementSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})

export const scheduleLineSchema = z.object({
  seq: z.number(),
  cheque_no: z.string(),
  cheque_date: date,
  amount: money,
  bank: bankSchema,
  status: z.enum(CHEQUE_STATUSES),
})
export type ScheduleLine = z.infer<typeof scheduleLineSchema>

export const schedulePreviewSchema = z.object({
  lines: z.array(scheduleLineSchema),
  annual_rent: money,
  total_cheque_value: money,
  cheque_count: z.number(),
  matches: z.boolean(),
  end_date: date.nullable().optional(),
})
export type SchedulePreview = z.infer<typeof schedulePreviewSchema>

export const scheduleSchema = z.object({
  agreement_id: z.string(),
  annual_rent: money,
  total_cheque_value: money,
  cheque_count: z.number(),
  matches: z.boolean(),
  pending: z.number(),
  cleared: z.number(),
  bounced: z.number(),
  items: z.array(chequeSchema),
})

export const renewalLinkSchema = z.object({
  id: z.string(),
  relation: z.enum(['previous', 'current', 'next']),
  start_date: date,
  end_date: date,
  annual_rent: money,
  cheque_count: z.number().nullable(),
  status: z.enum(AGREEMENT_STATUSES),
})
export type RenewalLink = z.infer<typeof renewalLinkSchema>

export const agreementDetailSchema = z.object({
  agreement: agreementSchema,
  schedule: scheduleSchema,
  renewals: z.array(renewalLinkSchema),
  history: z.array(auditEntrySchema),
})
export type AgreementDetail = z.infer<typeof agreementDetailSchema>

export const chequeDetailSchema = z.object({
  cheque: chequeSchema,
  agreement: agreementSchema,
  history: z.array(auditEntrySchema),
})
export type ChequeDetail = z.infer<typeof chequeDetailSchema>

export const renewalPreviewSchema = z.object({
  old: agreementSchema,
  start_date: date,
  end_date: date,
  annual_rent: money,
  old_annual_rent: money,
  cheque_count: z.number(),
  first_cheque_no: z.string(),
  first_cheque_date: date,
  bank: bankSchema,
  schedule: schedulePreviewSchema,
  old_pending_cheques: z.number(),
})
export type RenewalPreview = z.infer<typeof renewalPreviewSchema>

export const rentalSummarySchema = z.object({
  agreements_active: z.number(),
  expiring_30: z.number(),
  expired_unrenewed: z.number(),
  renewal_approaching: z.number(),
  annual_rent_active: money,
  cheques: chequeSummarySchema,
})
export type RentalSummary = z.infer<typeof rentalSummarySchema>

export const rentalAlertSchema = z.object({
  key: z.string(),
  kind: z.string(),
  severity: z.enum(['danger', 'warning']),
  title: z.string(),
  detail: z.string(),
  branch_name: z.string(),
  landlord: z.string(),
  cheque_no: z.string().nullable(),
  amount: money.nullable(),
  bank: bankSchema.nullable(),
  due_date: date.nullable(),
  days_remaining: z.number().nullable(),
  href: z.string(),
})
export type RentalAlert = z.infer<typeof rentalAlertSchema>
export const rentalAlertFeedSchema = z.object({
  items: z.array(rentalAlertSchema),
  total: z.number(),
  danger: z.number(),
  warning: z.number(),
})

/* ---------- Forms: client-side mirrors of the server rules, for fast feedback only. The API validates again. ---------- */
const reason = z.string().trim().min(3, 'Enter a reason (at least 3 characters)').max(500)
const optionalDate = z
  .string()
  .trim()
  .refine((v) => v === '' || isoDateSchema.safeParse(v).success, 'Use YYYY-MM-DD')

export const agreementFormSchema = z
  .object({
    branch_id: z.string().min(1, 'Choose a branch'),
    landlord: z.string().trim().min(1, 'Enter the landlord name').max(150),
    unit: z.string().trim().max(200),
    start_date: isoDateSchema,
    end_date: optionalDate,
    annual_rent: z
      .string()
      .trim()
      .min(1, 'Enter the annual rent')
      .pipe(aedAmountSchema)
      .refine((v) => Number(v) > 0, 'Annual rent must be more than 0'),
    cheque_count: z
      .string()
      .trim()
      .regex(/^\d+$/, 'Enter a whole number')
      .refine((v) => Number(v) >= 1 && Number(v) <= 12, 'Choose 1 to 12 cheques'),
    first_cheque_date: isoDateSchema,
    first_cheque_no: z.string().trim().min(1, 'Enter the first cheque number').max(50),
    bank: bankSchema,
    notes: z.string().trim().max(1000),
  })
  .refine((v) => v.end_date === '' || v.end_date > v.start_date, {
    path: ['end_date'],
    message: 'End date must be after the start date',
  })
export type AgreementFormInput = z.input<typeof agreementFormSchema>
export type AgreementFormValues = z.output<typeof agreementFormSchema>

export const agreementEditSchema = z.object({
  branch_id: z.string().min(1, 'Choose a branch'),
  landlord: z.string().trim().min(1, 'Enter the landlord name').max(150),
  unit: z.string().trim().max(200),
  start_date: isoDateSchema,
  end_date: isoDateSchema,
  notes: z.string().trim().max(1000),
  reason: z.string().trim().max(500),
})
export type AgreementEditInput = z.input<typeof agreementEditSchema>

export const replaceFormSchema = z.object({
  cheque_no: z.string().trim().min(1, 'Enter the new cheque number').max(50),
  cheque_date: optionalDate,
  bank: z.enum(['', ...RENTAL_BANKS]),
  notes: z.string().trim().max(500),
  reason,
})
export type ReplaceFormInput = z.input<typeof replaceFormSchema>

export const chequeEditSchema = z.object({
  cheque_no: z.string().trim().min(1, 'Enter the cheque number').max(50),
  cheque_date: isoDateSchema,
  bank: bankSchema,
  notes: z.string().trim().max(500),
  reason,
})
export type ChequeEditInput = z.input<typeof chequeEditSchema>

export const renewFormSchema = z.object({
  annual_rent: z
    .string()
    .trim()
    .refine(
      (v) => v === '' || aedAmountSchema.safeParse(v).success,
      'Enter a valid amount (max 2 decimals)',
    ),
  cheque_count: z
    .string()
    .trim()
    .refine(
      (v) => v === '' || (/^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 12),
      'Choose 1 to 12 cheques',
    ),
  first_cheque_date: optionalDate,
  first_cheque_no: z.string().trim().max(50),
  bank: z.enum(['', ...RENTAL_BANKS]),
})
export type RenewFormInput = z.input<typeof renewFormSchema>
