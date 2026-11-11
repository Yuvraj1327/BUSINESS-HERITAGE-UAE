import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/services/rentals.service'

/** Clearing a cheque moves bank balances, so a write refreshes rentals, cheques, alerts, Cash & Banks and the dashboard. */
function useInvalidateRentals() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['rentals', 'pdc', 'rental-alerts', 'cash-banks', 'dashboard', 'finance'].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    )
}
const q = { meta: { silent: true } } as const // screens show their own error state with a retry button

function useRentalMutation<V, R>(fn: (v: V) => Promise<R>) {
  const invalidate = useInvalidateRentals()
  return useMutation({ mutationFn: fn, meta: { silent: true }, onSuccess: invalidate })
}

/* ---------- agreements ---------- */
export const useRentalSummary = () =>
  useQuery({ queryKey: ['rentals', 'summary'], queryFn: api.getRentalSummary, ...q })
export const useAgreements = (f: api.AgreementFilters) =>
  useQuery({
    queryKey: ['rentals', 'list', f],
    queryFn: () => api.listAgreements(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useUpcomingExpiries = () =>
  useQuery({ queryKey: ['rentals', 'upcoming'], queryFn: () => api.listUpcomingExpiries(90), ...q })
export const useAgreement = (id: string) =>
  useQuery({ queryKey: ['rentals', 'detail', id], queryFn: () => api.getAgreement(id), ...q })
export const useSchedulePreview = () =>
  useMutation({ mutationFn: api.previewSchedule, meta: { silent: true } })
export const useCreateAgreement = () => useRentalMutation(api.createAgreement)
export const useUpdateAgreement = () =>
  useRentalMutation((v: { id: string; body: api.AgreementUpdatePayload }) =>
    api.updateAgreement(v.id, v.body),
  )
export const useRenewalPreview = () =>
  useMutation({
    mutationFn: (v: { id: string; body: api.RenewPayload }) => api.previewRenewal(v.id, v.body),
    meta: { silent: true },
  })
export const useRenewAgreement = () =>
  useRentalMutation((v: { id: string; body: api.RenewPayload & { expected_end_date: string } }) =>
    api.renewAgreement(v.id, v.body),
  )

/* ---------- cheques ---------- */
export const useChequeSummary = () =>
  useQuery({ queryKey: ['pdc', 'summary'], queryFn: api.getChequeSummary, ...q })
export const useCheques = (f: api.ChequeFilters) =>
  useQuery({
    queryKey: ['pdc', 'list', f],
    queryFn: () => api.listCheques(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useCheque = (id: string) =>
  useQuery({ queryKey: ['pdc', 'detail', id], queryFn: () => api.getCheque(id), ...q })
export const useClearCheque = () =>
  useRentalMutation((v: { id: string; cleared_date?: string; note?: string }) =>
    api.clearCheque(v.id, {
      ...(v.cleared_date ? { cleared_date: v.cleared_date } : {}),
      ...(v.note ? { note: v.note } : {}),
    }),
  )
export const useBounceCheque = () =>
  useRentalMutation((v: { id: string; bounced_date?: string; reason: string }) =>
    api.bounceCheque(v.id, {
      reason: v.reason,
      ...(v.bounced_date ? { bounced_date: v.bounced_date } : {}),
    }),
  )
export const useReplaceCheque = () =>
  useRentalMutation((v: { id: string; body: api.ReplacePayload }) =>
    api.replaceCheque(v.id, v.body),
  )
export const useUpdateCheque = () =>
  useRentalMutation((v: { id: string; body: api.ChequeUpdatePayload }) =>
    api.updateCheque(v.id, v.body),
  )

/* ---------- alerts (Owner only: Branch Users never call this) ---------- */
export const useRentalAlerts = (enabled = true) =>
  useQuery({
    queryKey: ['rental-alerts'],
    queryFn: api.getRentalAlerts,
    enabled,
    refetchInterval: 5 * 60_000,
    ...q,
  })
