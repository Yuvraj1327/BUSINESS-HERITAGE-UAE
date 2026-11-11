import { apiClient } from '@/lib/api-client'
import {
  accountsReportSchema,
  balancesSchema,
  branchCashReportSchema,
  categorySchema,
  auditEntrySchema,
  expenseDetailSchema,
  expensePageSchema,
  expenseSchema,
  ledgerPageSchema,
  openingBalancesSchema,
  settlementSchema,
  supplierEntryPageSchema,
  supplierEntrySchema,
  supplierPageSchema,
  supplierSchema,
  supplierSummarySchema,
  transferSchema,
  type PayAccount,
} from '@/schemas/finance'
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

/* ---------- opening balances ---------- */
export interface OpeningPayload {
  as_of_date: string
  receipts_bank: 'ENBD' | 'ADCB'
  enbd_balance: string
  adcb_balance: string
  pos_pending: string
  savings_brought_forward: string
  branch_cash: { branch_id: string; amount: string }[]
  supplier_dues: { supplier_id: string; amount: string }[]
  reason?: string
}
export const getOpeningBalances = () => get('/opening-balances', openingBalancesSchema)
export const saveOpeningBalances = (p: OpeningPayload) =>
  send('put', '/opening-balances', openingBalancesSchema, p)
export const getOpeningHistory = () => get('/opening-balances/history', z.array(auditEntrySchema))

/* ---------- cash & banks ---------- */
export interface LedgerFilters {
  date_from?: string
  date_to?: string
  account?: string
  branch_id?: string
  txn_type?: string
  page: number
  page_size: number
}
export const getBalances = (as_of?: string) => get('/cash-banks/summary', balancesSchema, { as_of })
export const getAccounts = (date_from?: string, date_to?: string) =>
  get('/cash-banks/accounts', accountsReportSchema, { date_from, date_to })
export const getBranchCash = (as_of?: string) =>
  get('/cash-banks/branches', branchCashReportSchema, { as_of })
export const getLedger = (f: LedgerFilters) =>
  get('/cash-banks/transactions', ledgerPageSchema, { ...f })
export const listTransfers = () => get('/cash-banks/transfers', z.array(transferSchema))
export const listSettlements = () => get('/cash-banks/pos-settlements', z.array(settlementSchema))
export interface TransferPayload {
  transfer_date: string
  from_account: PayAccount
  to_account: PayAccount
  branch_id?: string
  amount: string
  reference?: string
  note?: string
  client_key: string
}
export interface SettlementPayload {
  settlement_date: string
  bank: 'ENBD' | 'ADCB'
  amount: string
  reference?: string
  note?: string
  client_key: string
}
export const createTransfer = (p: TransferPayload) =>
  send('post', '/cash-banks/transfers', transferSchema, p)
export const createSettlement = (p: SettlementPayload) =>
  send('post', '/cash-banks/pos-settlements', settlementSchema, p)
export const voidTransfer = async (id: string, reason: string) => {
  await apiClient.post(`/cash-banks/transfers/${id}/void`, { reason })
}
export const voidSettlement = async (id: string, reason: string) => {
  await apiClient.post(`/cash-banks/pos-settlements/${id}/void`, { reason })
}

/* ---------- expenses ---------- */
export interface ExpenseFilters {
  date_from?: string
  date_to?: string
  branch_id?: string
  all_branches_only?: boolean
  category_id?: string
  paid_from?: string
  is_saving?: boolean
  include_voided?: boolean
  page: number
  page_size: number
}
export interface ExpensePayload {
  expense_date: string
  branch_id?: string
  category_id: string
  amount: string
  paid_from: PayAccount
  note?: string
  is_saving: boolean
  client_key: string
}
export const listExpenses = (f: ExpenseFilters) => get('/expenses', expensePageSchema, { ...f })
export const listCategories = () => get('/expenses/categories', z.array(categorySchema))
export const getExpense = (id: string) => get(`/expenses/${id}`, expenseDetailSchema)
export const createExpense = (p: ExpensePayload) => send('post', '/expenses', expenseSchema, p)
export const correctExpense = (
  id: string,
  p: Omit<ExpensePayload, 'client_key'> & { reason: string },
) => send('put', `/expenses/${id}`, expenseSchema, p)
export const voidExpense = async (id: string, reason: string) => {
  await apiClient.post(`/expenses/${id}/void`, { reason })
}
export const setExpenseSaving = (id: string, is_saving: boolean, reason: string) =>
  send('patch', `/expenses/${id}/saving`, expenseSchema, { is_saving, reason })

/* ---------- suppliers ---------- */
export interface SupplierFilters {
  q?: string
  status?: 'all' | 'active' | 'inactive'
  outstanding_only?: boolean
  sort: 'name' | 'outstanding' | 'paid' | 'created'
  desc: boolean
  page: number
  page_size: number
}
export interface SupplierPayload {
  name: string
  category?: string
  payment_terms?: string
  notes?: string
  is_active: boolean
  opening_outstanding?: string
}
export interface PaymentPayload {
  payment_date: string
  amount: string
  paid_from: PayAccount
  reference?: string
  note?: string
  client_key: string
}
export const getSupplierSummary = () => get('/suppliers/summary', supplierSummarySchema)
export const listSuppliers = (f: SupplierFilters) => get('/suppliers', supplierPageSchema, { ...f })
export const getSupplier = (id: string) => get(`/suppliers/${id}`, supplierSchema)
export const createSupplier = (p: SupplierPayload) => send('post', '/suppliers', supplierSchema, p)
export const updateSupplier = (id: string, p: Omit<SupplierPayload, 'opening_outstanding'>) =>
  send('put', `/suppliers/${id}`, supplierSchema, p)
export const listSupplierEntries = (
  id: string,
  f: { kind?: string; date_from?: string; date_to?: string; page: number; page_size: number },
) => get(`/suppliers/${id}/entries`, supplierEntryPageSchema, { ...f })
export const recordSupplierPayment = (id: string, p: PaymentPayload) =>
  send('post', `/suppliers/${id}/payments`, supplierEntrySchema, p)
export const markSupplierPaid = (
  id: string,
  p: {
    payment_date: string
    paid_from: PayAccount
    reference?: string
    note?: string
    client_key: string
  },
) => send('post', `/suppliers/${id}/mark-paid`, supplierEntrySchema, p)
export const voidSupplierEntry = async (entryId: string, reason: string) => {
  await apiClient.post(`/suppliers/entries/${entryId}/void`, { reason })
}

export const addSupplierDue = (
  id: string,
  p: { entry_date: string; amount: string; reference?: string; note?: string; client_key: string },
) => send('post', `/suppliers/${id}/dues`, supplierEntrySchema, p)
