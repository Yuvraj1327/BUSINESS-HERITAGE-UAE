import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/services/hr.service'

/** Employee / licence figures feed each other (cards, alerts, the Step 7 dashboard), so any write refreshes them all. */
function useInvalidateHr() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['employees', 'compliance', 'licenses', 'compliance-alerts', 'dashboard'].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    )
}
const q = { meta: { silent: true } } as const // screens show their own error state with a retry button

function useHrMutation<V, R>(fn: (v: V) => Promise<R>) {
  const invalidate = useInvalidateHr()
  return useMutation({ mutationFn: fn, meta: { silent: true }, onSuccess: invalidate })
}

/* ---------- employees ---------- */
export const useEmployeeSummary = () =>
  useQuery({ queryKey: ['employees', 'summary'], queryFn: api.getEmployeeSummary, ...q })
export const useLeaveSummary = () =>
  useQuery({ queryKey: ['employees', 'leave'], queryFn: api.getLeaveSummary, ...q })
export const useEmployees = (f: api.EmployeeFilters) =>
  useQuery({
    queryKey: ['employees', 'list', f],
    queryFn: () => api.listEmployees(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useEmployee = (id: string) =>
  useQuery({ queryKey: ['employees', 'detail', id], queryFn: () => api.getEmployee(id), ...q })
export const useCreateEmployee = () => useHrMutation(api.createEmployee)
export const useUpdateEmployee = () =>
  useHrMutation((v: { id: string; body: api.EmployeePayload }) => api.updateEmployee(v.id, v.body))
export const useChangeStatus = () =>
  useHrMutation((v: { id: string; body: api.StatusPayload }) =>
    api.changeEmployeeStatus(v.id, v.body),
  )
export const useReturnToWork = () =>
  useHrMutation((v: { id: string; return_date?: string; reason: string }) =>
    api.returnToWork(v.id, {
      reason: v.reason,
      ...(v.return_date ? { return_date: v.return_date } : {}),
    }),
  )
export const useCorrectLeave = () =>
  useHrMutation((v: { id: string; leave_start: string; reason: string }) =>
    api.correctLeave(v.id, { leave_start: v.leave_start, reason: v.reason }),
  )
export const useArchiveEmployee = () =>
  useHrMutation((v: { id: string; reason: string }) => api.archiveEmployee(v.id, v.reason))

/* ---------- visas & passports ---------- */
export const useComplianceSummary = () =>
  useQuery({ queryKey: ['compliance', 'summary'], queryFn: api.getComplianceSummary, ...q })
export const useCompliance = (kind: 'visas' | 'passports', f: api.ComplianceFilters) =>
  useQuery({
    queryKey: ['compliance', kind, f],
    queryFn: () => api.listCompliance(kind, f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useUpdateExpiry = () =>
  useHrMutation(
    (v: { id: string; kind: 'visa' | 'passport'; expiry_date: string; reason?: string }) =>
      api.updateExpiry(v.id, v.kind, {
        expiry_date: v.expiry_date,
        ...(v.reason ? { reason: v.reason } : {}),
      }),
  )
export const useExpiryHistory = (id: string) =>
  useQuery({
    queryKey: ['compliance', 'history', id],
    queryFn: () => api.getExpiryHistory(id),
    ...q,
  })

/* ---------- trade licenses ---------- */
export const useLicenseSummary = () =>
  useQuery({ queryKey: ['licenses', 'summary'], queryFn: api.getLicenseSummary, ...q })
export const useLicenses = (f: api.LicenseFilters) =>
  useQuery({
    queryKey: ['licenses', 'list', f],
    queryFn: () => api.listLicenses(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useLicense = (id: string) =>
  useQuery({ queryKey: ['licenses', 'detail', id], queryFn: () => api.getLicense(id), ...q })
export const useCreateLicense = () => useHrMutation(api.createLicense)
export const useUpdateLicense = () =>
  useHrMutation((v: { id: string; body: api.LicensePayload }) => api.updateLicense(v.id, v.body))
export const useRenewLicense = () =>
  useHrMutation((v: { id: string; body: api.RenewPayload }) => api.renewLicense(v.id, v.body))
export const useArchiveLicense = () =>
  useHrMutation((v: { id: string; reason: string }) => api.archiveLicense(v.id, v.reason))

/* ---------- alerts (Owner only: Branch Users never call this) ---------- */
export const useComplianceAlerts = (enabled: boolean) =>
  useQuery({
    queryKey: ['compliance-alerts'],
    queryFn: api.getComplianceAlerts,
    enabled,
    refetchInterval: 5 * 60_000,
    ...q,
  })
