import { apiClient } from '@/lib/api-client'
import {
  agreementDetailSchema,
  agreementPageSchema,
  chequeDetailSchema,
  chequePageSchema,
  chequeSummarySchema,
  renewalLinkSchema,
  renewalPreviewSchema,
  rentalAlertFeedSchema,
  rentalSummarySchema,
  scheduleSchema,
  schedulePreviewSchema,
  type AgreementStatus,
  type ChequeStatus,
  type RentalBank,
} from '@/schemas/rentals'
import { z } from 'zod'

type Params = Record<string, string | number | boolean | undefined>
const clean = (p: Params): Params =>
  Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined && v !== ''))
const get = async <T>(url: string, schema: z.ZodType<T>, params: Params = {}): Promise<T> =>
  schema.parse((await apiClient.get<unknown>(url, { params: clean(params) })).data)
const send = async <T>(
  method: 'post' | 'put' | 'patch',
  url: string,
  schema: z.ZodType<T>,
  body: unknown,
): Promise<T> => schema.parse((await apiClient[method]<unknown>(url, body)).data)

/* ---------- agreements ---------- */
export interface AgreementFilters {
  q?: string
  branch_id?: string
  status?: AgreementStatus
  sort: 'end' | 'start' | 'branch' | 'landlord' | 'rent'
  desc: boolean
  page: number
  page_size: number
}
export interface ChequeLinePayload {
  cheque_no: string
  cheque_date: string
  amount: string
  bank: RentalBank
}
export interface SchedulePayload {
  annual_rent: string
  cheque_count: number
  first_cheque_date: string
  first_cheque_no: string
  bank: RentalBank
}
export interface AgreementPayload extends SchedulePayload {
  branch_id: string
  landlord: string
  unit?: string
  start_date: string
  end_date?: string
  notes?: string
  cheques?: ChequeLinePayload[]
}
export interface AgreementUpdatePayload {
  branch_id: string
  landlord: string
  unit?: string
  start_date: string
  end_date: string
  notes?: string
  reason?: string
}
export interface RenewPayload {
  annual_rent?: string
  cheque_count?: number
  first_cheque_date?: string
  first_cheque_no?: string
  bank?: RentalBank
  notes?: string
}

export const getRentalSummary = () => get('/rentals/summary', rentalSummarySchema)
export const getRentalAlerts = () => get('/rentals/alerts', rentalAlertFeedSchema)
export const listAgreements = (f: AgreementFilters) =>
  get('/rentals', agreementPageSchema, { ...f })
export const listUpcomingExpiries = (days = 90) =>
  get('/rentals/upcoming-expiries', agreementPageSchema, { days, page_size: 10 })
export const getAgreement = (id: string) => get(`/rentals/${id}`, agreementDetailSchema)
export const getAgreementSchedule = (id: string) => get(`/rentals/${id}/schedule`, scheduleSchema)
export const getRenewals = (id: string) =>
  get(`/rentals/${id}/renewals`, z.array(renewalLinkSchema))
export const previewSchedule = (b: SchedulePayload) =>
  send('post', '/rentals/schedule-preview', schedulePreviewSchema, b)
export const createAgreement = (b: AgreementPayload) =>
  send('post', '/rentals', agreementDetailSchema, b)
export const updateAgreement = (id: string, b: AgreementUpdatePayload) =>
  send('put', `/rentals/${id}`, agreementDetailSchema, b)
export const previewRenewal = (id: string, b: RenewPayload) =>
  send('post', `/rentals/${id}/renewal-preview`, renewalPreviewSchema, b)
export const renewAgreement = (id: string, b: RenewPayload & { expected_end_date: string }) =>
  send('post', `/rentals/${id}/renew`, agreementDetailSchema, { ...b, confirm: true })

/* ---------- cheques ---------- */
export interface ChequeFilters {
  q?: string
  branch_id?: string
  bank?: RentalBank
  status?: ChequeStatus
  view?: 'overdue' | 'upcoming' | 'bounced_open'
  date_from?: string
  date_to?: string
  agreement_id?: string
  sort: 'date' | 'number' | 'amount' | 'branch' | 'landlord'
  desc: boolean
  page: number
  page_size: number
}
export const getChequeSummary = () => get('/pdc-cheques/summary', chequeSummarySchema)
export const listCheques = (f: ChequeFilters) => get('/pdc-cheques', chequePageSchema, { ...f })
export const getCheque = (id: string) => get(`/pdc-cheques/${id}`, chequeDetailSchema)
export const clearCheque = (id: string, b: { cleared_date?: string; note?: string }) =>
  send('post', `/pdc-cheques/${id}/clear`, chequeDetailSchema, b)
export const bounceCheque = (id: string, b: { bounced_date?: string; reason: string }) =>
  send('post', `/pdc-cheques/${id}/bounce`, chequeDetailSchema, b)
export interface ReplacePayload {
  cheque_no: string
  cheque_date?: string
  bank?: RentalBank
  notes?: string
  reason: string
}
export const replaceCheque = (id: string, b: ReplacePayload) =>
  send('post', `/pdc-cheques/${id}/replace`, chequeDetailSchema, b)
export interface ChequeUpdatePayload {
  cheque_no: string
  cheque_date: string
  bank: RentalBank
  notes?: string
  reason: string
}
export const updateCheque = (id: string, b: ChequeUpdatePayload) =>
  send('patch', `/pdc-cheques/${id}`, chequeDetailSchema, b)
