import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/services/orders.service'

const quiet = { meta: { silent: true } } as const
const K = 'orders'

export const useOrders = (f: api.OrderFilters) =>
  useQuery({
    queryKey: [K, 'list', f],
    queryFn: () => api.listOrders(f),
    placeholderData: keepPreviousData,
    ...quiet,
  })
export const useOrder = (id: string) =>
  useQuery({
    queryKey: [K, 'detail', id],
    queryFn: () => api.getOrder(id),
    enabled: id !== '',
    ...quiet,
  })
export const useCategories = () =>
  useQuery({
    queryKey: [K, 'categories'],
    queryFn: api.getCategories,
    staleTime: 300_000,
    ...quiet,
  })
export const useOrderDashboard = (p: { date?: string; branch_id?: string }) =>
  useQuery({
    queryKey: [K, 'dashboard', p],
    queryFn: () => api.getDashboard(p),
    placeholderData: keepPreviousData,
    ...quiet,
  })
export const usePaymentSummary = (p: { date_from: string; date_to: string; branch_id?: string }) =>
  useQuery({ queryKey: [K, 'paysum', p], queryFn: () => api.getPaymentSummary(p), ...quiet })

export const useCustomers = (p: {
  q?: string
  branch_id?: string
  page: number
  page_size?: number
}) =>
  useQuery({
    queryKey: [K, 'customers', p],
    queryFn: () => api.listCustomers(p),
    placeholderData: keepPreviousData,
    ...quiet,
  })
export const useCustomer = (id: string) =>
  useQuery({
    queryKey: [K, 'customer', id],
    queryFn: () => api.getCustomer(id),
    enabled: id !== '',
    ...quiet,
  })
export const useCustomerOrders = (id: string, page: number) =>
  useQuery({
    queryKey: [K, 'customer-orders', id, page],
    queryFn: () => api.listCustomerOrders(id, page),
    enabled: id !== '',
    placeholderData: keepPreviousData,
    ...quiet,
  })

export const useOpsCounts = (p: { date?: string; branch_id?: string }) =>
  useQuery({
    queryKey: [K, 'ops-counts', p],
    queryFn: () => api.getOpsCounts(p),
    placeholderData: keepPreviousData,
    ...quiet,
  })
export const useOpsView = (view: string, p: api.OpsQuery) =>
  useQuery({
    queryKey: [K, 'ops', view, p],
    queryFn: () => api.getOpsView(view, p),
    placeholderData: keepPreviousData,
    ...quiet,
  })

export const useOrderReportCatalog = () =>
  useQuery({
    queryKey: [K, 'report-catalog'],
    queryFn: api.getOrderReportCatalog,
    staleTime: 600_000,
    ...quiet,
  })
export const useOrderReport = (
  key: string,
  f: api.OrderReportFilters & { page: number; page_size: number },
) =>
  useQuery({
    queryKey: [K, 'report', key, f],
    queryFn: () => api.getOrderReport(key, f),
    placeholderData: keepPreviousData,
    enabled: key !== '',
    ...quiet,
  })
export const useOrderExport = () =>
  useMutation({
    mutationFn: (v: { key: string; format: 'csv' | 'xlsx'; filters: api.OrderReportFilters }) =>
      api.downloadOrderExport(v.key, v.format, v.filters),
    meta: { silent: true },
  })

/** Every order write refreshes everything order-shaped (lists, dashboard, operations, reports, customers). */
function useInvalidate() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: [K] })
}
export const useCreateOrder = () => {
  const done = useInvalidate()
  return useMutation({
    mutationFn: api.createOrder,
    onSuccess: done,
    meta: { silent: true },
  })
}
export const useUpdateOrder = (id: string) => {
  const done = useInvalidate()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateOrder(id, body),
    onSuccess: done,
    meta: { silent: true },
  })
}
export const useSetStatus = (id: string) => {
  const done = useInvalidate()
  return useMutation({
    mutationFn: (v: { status: string; note?: string }) => api.setStatus(id, v.status, v.note),
    onSuccess: done,
    meta: { silent: true },
  })
}
export const useCancelOrder = (id: string) => {
  const done = useInvalidate()
  return useMutation({
    mutationFn: (reason: string) => api.cancelOrder(id, reason),
    onSuccess: done,
    meta: { silent: true },
  })
}
export const useAddPayment = (id: string) => {
  const done = useInvalidate()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.addPayment(id, body),
    onSuccess: done,
    meta: { silent: true },
  })
}
export const useCreateCustomer = () => {
  const done = useInvalidate()
  return useMutation({ mutationFn: api.createCustomer, onSuccess: done, meta: { silent: true } })
}
export const useUpdateCustomer = (id: string) => {
  const done = useInvalidate()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateCustomer(id, body),
    onSuccess: done,
    meta: { silent: true },
  })
}
