import { apiClient } from '@/lib/api-client'
import {
  alertFeedSchema,
  compliancePageSchema,
  complianceSummarySchema,
  employeeDetailSchema,
  employeePageSchema,
  employeeSummarySchema,
  expiryHistorySchema,
  leaveSummarySchema,
  licenseDetailSchema,
  licensePageSchema,
  licenseSummarySchema,
  renewalSchema,
  type EmploymentStatus,
} from '@/schemas/hr'
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

/* ---------- employees ---------- */
export interface EmployeeFilters {
  q?: string
  branch_id?: string
  status?: EmploymentStatus
  sort: 'name' | 'branch' | 'role' | 'salary' | 'status' | 'created'
  desc: boolean
  page: number
  page_size: number
}
export const getEmployeeSummary = () => get('/employees/summary', employeeSummarySchema)
export const getLeaveSummary = () => get('/employees/leave/summary', leaveSummarySchema)
export const listEmployees = (f: EmployeeFilters) => get('/employees', employeePageSchema, { ...f })
export const getEmployee = (id: string) => get(`/employees/${id}`, employeeDetailSchema)
export interface EmployeePayload {
  full_name: string
  branch_id: string
  role_title?: string
  monthly_salary: string
  passport_expiry?: string
  visa_expiry?: string
  notes?: string
  reason?: string
}
export const createEmployee = (b: EmployeePayload) =>
  send('post', '/employees', employeeDetailSchema, b)
export const updateEmployee = (id: string, b: EmployeePayload) =>
  send('put', `/employees/${id}`, employeeDetailSchema, b)
export interface StatusPayload {
  status: EmploymentStatus
  leave_start?: string
  return_date?: string
  cancellation_date?: string
  reason: string
}
export const changeEmployeeStatus = (id: string, b: StatusPayload) =>
  send('post', `/employees/${id}/status`, employeeDetailSchema, b)
export const returnToWork = (id: string, b: { return_date?: string; reason: string }) =>
  send('post', `/employees/${id}/return`, employeeDetailSchema, b)
export const correctLeave = (id: string, b: { leave_start: string; reason: string }) =>
  send('patch', `/employees/${id}/leave`, employeeDetailSchema, b)
export const archiveEmployee = async (id: string, reason: string) => {
  await apiClient.post(`/employees/${id}/archive`, { reason })
}

/* ---------- visas & passports ---------- */
export interface ComplianceFilters {
  q?: string
  branch_id?: string
  bucket?: string
  sort: 'expiry' | 'name' | 'branch'
  desc: boolean
  page: number
  page_size: number
}
export const getComplianceSummary = () => get('/visas-passports/summary', complianceSummarySchema)
export const listCompliance = (kind: 'visas' | 'passports', f: ComplianceFilters) =>
  get(`/visas-passports/${kind}`, compliancePageSchema, { ...f })
export const updateExpiry = (
  id: string,
  kind: 'visa' | 'passport',
  b: { expiry_date: string; reason?: string },
) => send('patch', `/visas-passports/employees/${id}/${kind}-expiry`, employeeDetailSchema, b)
export const getExpiryHistory = (id: string) =>
  get(`/visas-passports/employees/${id}/history`, expiryHistorySchema)

/* ---------- trade licenses ---------- */
export interface LicenseFilters {
  q?: string
  branch_id?: string
  status?: string
  sort: 'expiry' | 'branch' | 'number' | 'fee'
  desc: boolean
  page: number
  page_size: number
}
export const getLicenseSummary = () => get('/trade-licenses/summary', licenseSummarySchema)
export const listLicenses = (f: LicenseFilters) =>
  get('/trade-licenses', licensePageSchema, { ...f })
export const getLicense = (id: string) => get(`/trade-licenses/${id}`, licenseDetailSchema)
export interface LicensePayload {
  branch_id: string
  license_no: string
  authority?: string
  expiry_date: string
  renewal_fee: string
  notes?: string
  reason?: string
}
export const createLicense = (b: LicensePayload) =>
  send('post', '/trade-licenses', licenseDetailSchema, b)
export const updateLicense = (id: string, b: LicensePayload) =>
  send('put', `/trade-licenses/${id}`, licenseDetailSchema, b)
export interface RenewPayload {
  expected_expiry: string
  renewal_fee?: string
  note?: string
  client_key: string
}
export const renewLicense = (id: string, b: RenewPayload) =>
  send('post', `/trade-licenses/${id}/renew`, licenseDetailSchema, b)
export const listRenewals = (id: string) =>
  get(`/trade-licenses/${id}/renewals`, z.array(renewalSchema))
export const archiveLicense = async (id: string, reason: string) => {
  await apiClient.post(`/trade-licenses/${id}/archive`, { reason })
}

/* ---------- alerts ---------- */
export const getComplianceAlerts = () => get('/compliance/alerts', alertFeedSchema)
