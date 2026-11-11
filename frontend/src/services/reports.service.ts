import { apiClient } from '@/lib/api-client'
import { dailyReportPageSchema, dailyReportSchema } from '@/schemas/reports'
import type { DailyReport, DailyReportPage } from '@/schemas/reports'

export interface ReportPayload {
  report_date: string
  branch_id?: string
  total_sales: string
  order_count: number
  cash_received: string
  pos_amount: string
  bank_transfer: string
  link_payment: string
  shop_expenses: string
  shop_savings: string
}

export interface ReportFilters {
  branch_id?: string
  date_from?: string
  date_to?: string
  page: number
  page_size: number
}

export async function createDailyReport(payload: ReportPayload): Promise<DailyReport> {
  const { data } = await apiClient.post<unknown>('/daily-reports', payload)
  return dailyReportSchema.parse(data)
}

export async function listDailyReports(filters: ReportFilters): Promise<DailyReportPage> {
  const { data } = await apiClient.get<unknown>('/daily-reports', { params: filters })
  return dailyReportPageSchema.parse(data)
}

export async function voidDailyReport(id: string, reason: string): Promise<void> {
  await apiClient.post(`/daily-reports/${id}/void`, { reason })
}
