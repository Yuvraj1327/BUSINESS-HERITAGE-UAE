import { apiClient } from '@/lib/api-client'
import {
  balanceSchema,
  categoriesSchema,
  countsSchema,
  customerPageSchema,
  customerSchema,
  dashboardSchema,
  orderDetailSchema,
  orderPageSchema,
  orderReportCatalogSchema,
  orderReportSchema,
  paymentSummarySchema,
  historySchema,
} from '@/schemas/orders'
import { z } from 'zod'

type Params = Record<string, string | number | boolean | undefined>
const clean = (p: Params): Params =>
  Object.fromEntries(
    Object.entries(p).filter(([, v]) => v !== undefined && v !== '' && v !== 'all'),
  )

export interface OrderFilters {
  q?: string
  branch_id?: string
  status?: string
  payment_status?: string
  category_id?: string
  service_type?: string
  area?: string
  date_from?: string
  date_to?: string
  pickup_date?: string
  delivery_date?: string
  sort?: string
  desc?: boolean
  page: number
  page_size: number
}

export const listOrders = async (f: OrderFilters) =>
  orderPageSchema.parse((await apiClient.get<unknown>('/orders', { params: clean({ ...f }) })).data)
export const getOrder = async (id: string) =>
  orderDetailSchema.parse((await apiClient.get<unknown>(`/orders/${id}`)).data)
export const getCategories = async () =>
  categoriesSchema.parse((await apiClient.get<unknown>('/orders/service-categories')).data)
export const getDashboard = async (p: { date?: string; branch_id?: string }) =>
  dashboardSchema.parse(
    (await apiClient.get<unknown>('/orders/dashboard', { params: clean({ ...p }) })).data,
  )
export const getPaymentSummary = async (p: {
  date_from: string
  date_to: string
  branch_id?: string
}) =>
  paymentSummarySchema.parse(
    (await apiClient.get<unknown>('/orders/payments/summary', { params: clean({ ...p }) })).data,
  )
export const getStatusHistory = async (id: string) =>
  z.array(historySchema).parse((await apiClient.get<unknown>(`/orders/${id}/status-history`)).data)

export const createOrder = async (body: Record<string, unknown>) =>
  orderDetailSchema.parse((await apiClient.post<unknown>('/orders', body)).data)
export const updateOrder = async (id: string, body: Record<string, unknown>) =>
  orderDetailSchema.parse((await apiClient.put<unknown>(`/orders/${id}`, body)).data)
export const setStatus = async (id: string, status: string, note?: string) =>
  orderDetailSchema.parse(
    (await apiClient.post<unknown>(`/orders/${id}/status`, { status, note: note || null })).data,
  )
export const cancelOrder = async (id: string, reason: string) =>
  orderDetailSchema.parse(
    (await apiClient.post<unknown>(`/orders/${id}/cancel`, { reason, confirm: true })).data,
  )
/** The server answers with the new balance; the page refetches the order for the full payment list. */
export const addPayment = async (id: string, body: Record<string, unknown>) =>
  balanceSchema.parse((await apiClient.post<unknown>(`/orders/${id}/payments`, body)).data)

// customers
export const listCustomers = async (p: {
  q?: string
  branch_id?: string
  page: number
  page_size?: number
}) =>
  customerPageSchema.parse(
    (await apiClient.get<unknown>('/customers', { params: clean({ ...p }) })).data,
  )
export const getCustomer = async (id: string) =>
  customerSchema.parse((await apiClient.get<unknown>(`/customers/${id}`)).data)
export const createCustomer = async (body: Record<string, unknown>) =>
  customerSchema.parse((await apiClient.post<unknown>('/customers', body)).data)
export const updateCustomer = async (id: string, body: Record<string, unknown>) =>
  customerSchema.parse((await apiClient.put<unknown>(`/customers/${id}`, body)).data)
export const listCustomerOrders = async (id: string, page = 1) =>
  orderPageSchema.parse(
    (await apiClient.get<unknown>(`/customers/${id}/orders`, { params: { page } })).data,
  )

// operations
export interface OpsQuery {
  date?: string
  branch_id?: string
  q?: string
  sort?: string
  desc?: boolean
  page: number
  page_size: number
}
export const getOpsCounts = async (p: { date?: string; branch_id?: string }) =>
  countsSchema.parse(
    (await apiClient.get<unknown>('/order-operations/counts', { params: clean({ ...p }) })).data,
  )
export const getOpsView = async (view: string, p: OpsQuery) =>
  orderPageSchema.parse(
    (await apiClient.get<unknown>(`/order-operations/${view}`, { params: clean({ ...p }) })).data,
  )

// reports
export interface OrderReportFilters {
  date_from: string
  date_to: string
  period: 'day' | 'week'
  branch_id?: string
  sort?: string
  desc?: boolean
}
export const getOrderReportCatalog = async () =>
  orderReportCatalogSchema.parse((await apiClient.get<unknown>('/orders/reports/catalog')).data)
export const getOrderReport = async (
  key: string,
  f: OrderReportFilters & { page: number; page_size: number },
) =>
  orderReportSchema.parse(
    (await apiClient.get<unknown>(`/orders/reports/${key}`, { params: clean({ ...f }) })).data,
  )

/** The server builds the file from the same filters (and the same branch scope); the browser only saves it. */
export async function downloadOrderExport(
  key: string,
  format: 'csv' | 'xlsx',
  f: OrderReportFilters,
): Promise<string> {
  const res = await apiClient.get<Blob>(`/orders/reports/${key}/export`, {
    params: clean({ ...f, format }),
    responseType: 'blob',
    timeout: 120_000,
  })
  const header = String(res.headers['content-disposition'] ?? '')
  const name = /filename="?([^";]+)"?/.exec(header)?.[1] ?? `${key}.${format}`
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  return name
}
