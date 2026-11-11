import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/services/alerts.service'

const q = { meta: { silent: true } } as const

/** Every alert read re-syncs on the server, so the bell also polls lightly while the app is open. */
export const useAlertSummary = (enabled = true) =>
  useQuery({
    queryKey: ['alerts', 'summary'],
    queryFn: api.getAlertSummary,
    enabled,
    refetchInterval: 120_000,
    ...q,
  })
export const useAlertFacets = () =>
  useQuery({
    queryKey: ['alerts', 'facets'],
    queryFn: api.getAlertFacets,
    staleTime: 300_000,
    ...q,
  })
export const useAlerts = (scope: 'active' | 'history', f: api.AlertFilters) =>
  useQuery({
    queryKey: ['alerts', 'list', scope, f],
    queryFn: () => api.listAlerts(scope, f),
    placeholderData: keepPreviousData,
    ...q,
  })

function useAlertMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    meta: { silent: true },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}
export const useMarkRead = () => useAlertMutation(api.markAlertRead)
export const useAcknowledge = () => useAlertMutation(api.acknowledgeAlert)
export const useReadAll = () => useAlertMutation(api.readAllAlerts)
export const useRefreshAlerts = () => useAlertMutation(api.refreshAlerts)
