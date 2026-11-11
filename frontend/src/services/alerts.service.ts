import { apiClient } from '@/lib/api-client'
import {
  alertFacetsSchema,
  alertPageSchema,
  alertSchema,
  alertSummarySchema,
  unreadCountSchema,
  type AlertSeverity,
} from '@/schemas/alerts'

type Params = Record<string, string | number | boolean | undefined>
const clean = (p: Params): Params =>
  Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined && v !== ''))

export interface AlertFilters {
  q?: string
  kind?: string
  severity?: AlertSeverity
  branch_id?: string
  module?: string
  status?: string
  page: number
  page_size: number
}

export const getAlertSummary = async () =>
  alertSummarySchema.parse((await apiClient.get<unknown>('/alerts/summary')).data)
export const getAlertFacets = async () =>
  alertFacetsSchema.parse((await apiClient.get<unknown>('/alerts/facets')).data)
export const listAlerts = async (scope: 'active' | 'history', f: AlertFilters) =>
  alertPageSchema.parse(
    (
      await apiClient.get<unknown>(scope === 'active' ? '/alerts' : '/alerts/history', {
        params: clean({ ...f }),
      })
    ).data,
  )
export const markAlertRead = async (id: string) =>
  alertSchema.parse((await apiClient.post<unknown>(`/alerts/${id}/read`, {})).data)
export const acknowledgeAlert = async (id: string) =>
  alertSchema.parse((await apiClient.post<unknown>(`/alerts/${id}/acknowledge`, {})).data)
export const readAllAlerts = async () =>
  unreadCountSchema.parse((await apiClient.post<unknown>('/alerts/read-all', {})).data)
export const refreshAlerts = async () =>
  unreadCountSchema.parse((await apiClient.post<unknown>('/alerts/refresh', {})).data)
