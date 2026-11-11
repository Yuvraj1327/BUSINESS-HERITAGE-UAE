import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import * as api from '@/services/analytics.service'

const q = { meta: { silent: true } } as const

export const useCatalog = () =>
  useQuery({
    queryKey: ['analytics', 'catalog'],
    queryFn: api.getCatalog,
    staleTime: 600_000,
    ...q,
  })
export const useOverview = (f: api.ReportFilters) =>
  useQuery({
    queryKey: ['analytics', 'overview', f],
    queryFn: () => api.getOverview(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useCharts = (f: api.ReportFilters, enabled = true) =>
  useQuery({
    queryKey: ['analytics', 'charts', f],
    queryFn: () => api.getCharts(f),
    placeholderData: keepPreviousData,
    enabled,
    ...q,
  })
export const useReport = (key: string, f: api.ReportQuery) =>
  useQuery({
    queryKey: ['analytics', 'report', key, f],
    queryFn: () => api.getReport(key, f),
    placeholderData: keepPreviousData,
    enabled: key !== '',
    ...q,
  })
export const useActors = () =>
  useQuery({ queryKey: ['analytics', 'actors'], queryFn: api.getActors, ...q })
export const useExport = () =>
  useMutation({
    mutationFn: (v: {
      key: string
      format: 'csv' | 'xlsx'
      filters: api.ReportFilters & { sort?: string; desc?: boolean }
    }) => api.downloadExport(v.key, v.format, v.filters),
    meta: { silent: true },
  })
