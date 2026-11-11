import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/services/finance.service'

/** Every figure that comes from the finance ledger is stale after any finance write; so are the Step 7 balances. */
function useInvalidateFinance() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['opening', 'cash-banks', 'expenses', 'suppliers', 'dashboard', 'branch-date-view'].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    )
}

const q = { meta: { silent: true } } as const // screens show their own error state with a retry button

/* ---------- opening balances ---------- */
export const useOpeningBalances = () =>
  useQuery({ queryKey: ['opening', 'current'], queryFn: api.getOpeningBalances, ...q })
export const useOpeningHistory = (enabled: boolean) =>
  useQuery({ queryKey: ['opening', 'history'], queryFn: api.getOpeningHistory, enabled, ...q })
export function useSaveOpeningBalances() {
  const invalidate = useInvalidateFinance()
  return useMutation({
    mutationFn: api.saveOpeningBalances,
    meta: { silent: true },
    onSuccess: invalidate,
  })
}

/* ---------- cash & banks ---------- */
export const useBalances = () =>
  useQuery({ queryKey: ['cash-banks', 'summary'], queryFn: () => api.getBalances(), ...q })
export const useAccountsReport = (from: string, to: string, enabled = true) =>
  useQuery({
    queryKey: ['cash-banks', 'accounts', from, to],
    queryFn: () => api.getAccounts(from || undefined, to || undefined),
    enabled,
    placeholderData: keepPreviousData,
    ...q,
  })
export const useBranchCash = () =>
  useQuery({ queryKey: ['cash-banks', 'branches'], queryFn: () => api.getBranchCash(), ...q })
export const useLedger = (f: api.LedgerFilters, enabled = true) =>
  useQuery({
    queryKey: ['cash-banks', 'ledger', f],
    queryFn: () => api.getLedger(f),
    enabled,
    placeholderData: keepPreviousData,
    ...q,
  })
export const useTransfers = () =>
  useQuery({ queryKey: ['cash-banks', 'transfers'], queryFn: api.listTransfers, ...q })
export const useSettlements = () =>
  useQuery({ queryKey: ['cash-banks', 'settlements'], queryFn: api.listSettlements, ...q })

function useFinanceMutation<V, R>(fn: (v: V) => Promise<R>) {
  const invalidate = useInvalidateFinance()
  return useMutation({ mutationFn: fn, meta: { silent: true }, onSuccess: invalidate })
}
export const useCreateTransfer = () => useFinanceMutation(api.createTransfer)
export const useCreateSettlement = () => useFinanceMutation(api.createSettlement)
export const useVoidTransfer = () =>
  useFinanceMutation((v: { id: string; reason: string }) => api.voidTransfer(v.id, v.reason))
export const useVoidSettlement = () =>
  useFinanceMutation((v: { id: string; reason: string }) => api.voidSettlement(v.id, v.reason))

/* ---------- expenses ---------- */
export const useExpenses = (f: api.ExpenseFilters) =>
  useQuery({
    queryKey: ['expenses', 'list', f],
    queryFn: () => api.listExpenses(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useCategories = () =>
  useQuery({
    queryKey: ['expenses', 'categories'],
    queryFn: api.listCategories,
    staleTime: 5 * 60_000,
    ...q,
  })
export const useExpense = (id: string | null) =>
  useQuery({
    queryKey: ['expenses', 'detail', id],
    queryFn: () => api.getExpense(id as string),
    enabled: id !== null,
    ...q,
  })
export const useCreateExpense = () => useFinanceMutation(api.createExpense)
export const useCorrectExpense = () =>
  useFinanceMutation((v: { id: string; body: Parameters<typeof api.correctExpense>[1] }) =>
    api.correctExpense(v.id, v.body),
  )
export const useVoidExpense = () =>
  useFinanceMutation((v: { id: string; reason: string }) => api.voidExpense(v.id, v.reason))
export const useSetSaving = () =>
  useFinanceMutation((v: { id: string; is_saving: boolean; reason: string }) =>
    api.setExpenseSaving(v.id, v.is_saving, v.reason),
  )

/* ---------- suppliers ---------- */
export const useSupplierSummary = () =>
  useQuery({ queryKey: ['suppliers', 'summary'], queryFn: api.getSupplierSummary, ...q })
export const useSuppliers = (f: api.SupplierFilters) =>
  useQuery({
    queryKey: ['suppliers', 'list', f],
    queryFn: () => api.listSuppliers(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useSupplier = (id: string) =>
  useQuery({ queryKey: ['suppliers', 'detail', id], queryFn: () => api.getSupplier(id), ...q })
export const useSupplierEntries = (id: string, f: Parameters<typeof api.listSupplierEntries>[1]) =>
  useQuery({
    queryKey: ['suppliers', 'entries', id, f],
    queryFn: () => api.listSupplierEntries(id, f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useCreateSupplier = () => useFinanceMutation(api.createSupplier)
export const useUpdateSupplier = () =>
  useFinanceMutation((v: { id: string; body: Parameters<typeof api.updateSupplier>[1] }) =>
    api.updateSupplier(v.id, v.body),
  )
export const useRecordPayment = () =>
  useFinanceMutation((v: { id: string; body: api.PaymentPayload }) =>
    api.recordSupplierPayment(v.id, v.body),
  )
export const useMarkPaid = () =>
  useFinanceMutation((v: { id: string; body: Parameters<typeof api.markSupplierPaid>[1] }) =>
    api.markSupplierPaid(v.id, v.body),
  )
export const useVoidSupplierEntry = () =>
  useFinanceMutation((v: { id: string; reason: string }) => api.voidSupplierEntry(v.id, v.reason))
export const useAddDue = () =>
  useFinanceMutation((v: { id: string; body: Parameters<typeof api.addSupplierDue>[1] }) =>
    api.addSupplierDue(v.id, v.body),
  )
