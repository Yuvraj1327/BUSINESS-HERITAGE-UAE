import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { AuthProvider } from '@/auth/AuthProvider'
import { MODULES } from '@/auth/permissions'
import { apiClient } from '@/lib/api-client'
import { appRoutes } from '@/routes'

export interface ApiReply {
  status: number
  body: unknown
}

/** Replaces the HTTP transport so the REAL axios interceptors (token, 401 handling) still run. */
export function stubApi(handler: (config: InternalAxiosRequestConfig) => ApiReply) {
  const calls: InternalAxiosRequestConfig[] = []
  apiClient.defaults.adapter = async (config) => {
    calls.push(config)
    const { status, body } = handler(config)
    const response = { data: body, status, statusText: '', headers: {}, config } as AxiosResponse
    if (status >= 400) throw new AxiosError('failed', 'ERR_BAD_RESPONSE', config, null, response)
    return response
  }
  return calls
}

// Mock of what the server sends for an Owner: every module, all branches (matches backend PERMISSION_MATRIX).
const OWNER_PERMS = Object.fromEntries(
  MODULES.map((m) => [
    m,
    { actions: ['read', 'create', 'update', 'export', 'manage'], scope: 'all_branches' },
  ]),
)
// Mock of what the server sends for a Branch User (matches backend PERMISSION_MATRIX).
const BRANCH_PERMS = {
  dashboard: { actions: ['read'], scope: 'own_branch' },
  branch_management: { actions: ['read'], scope: 'own_branch' },
  daily_reports: { actions: ['create', 'read'], scope: 'own_branch' },
  orders: { actions: ['create', 'export', 'read', 'update'], scope: 'own_branch' },
  customers: { actions: ['create', 'read', 'update'], scope: 'own_branch' },
  order_payments: { actions: ['create', 'read'], scope: 'own_branch' },
}

export const PROFILE_OWNER = {
  user_id: '11111111-1111-4111-8111-111111111111',
  full_name: 'Test Owner',
  role: 'owner',
  branch_id: null,
  branch_name: null,
  is_active: true,
  permissions: OWNER_PERMS,
}

export const PROFILE_BRANCH = {
  user_id: '11111111-1111-4111-8111-111111111111',
  full_name: 'Test Branch User',
  role: 'branch',
  branch_id: '22222222-2222-4222-8222-222222222222',
  branch_name: 'SATWA',
  is_active: true,
  permissions: BRANCH_PERMS,
}

/** Central alert feed (GET /alerts/summary) as the server sends it. */
export const alertItem = (over: Record<string, unknown> = {}) => ({
  id: 'al1',
  alert_key: 'task_overdue:t1',
  kind: 'task_overdue',
  type_label: 'Task overdue',
  module: 'tasks',
  title: 'Task overdue',
  detail: 'Renew water contract (ALSAFA MAIN, Unassigned): 2 days overdue',
  record_id: 't1',
  branch_id: null,
  branch_name: 'ALSAFA MAIN',
  alert_date: '2026-11-08',
  due_date: '2026-11-08',
  severity: 'warning',
  status: 'unread',
  href: '/tasks/t1',
  first_seen_at: '2026-11-10T06:00:00Z',
  last_seen_at: '2026-11-10T06:00:00Z',
  read_at: null,
  acknowledged_at: null,
  resolved_at: null,
  ...over,
})
export const alertSummary = (items: unknown[] = []) => ({
  total_active: items.length,
  critical: items.filter((i) => (i as { severity: string }).severity === 'critical').length,
  warning: items.filter((i) => (i as { severity: string }).severity === 'warning').length,
  info: items.filter((i) => (i as { severity: string }).severity === 'info').length,
  unread: items.length,
  acknowledged: 0,
  recent: items,
  by_module: {},
})

export const apiError = (status: number, code: string, message = 'msg'): ApiReply => ({
  status,
  body: { error: { code, message, fields: null }, request_id: 'r1' },
})

export function renderApp(path = '/') {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return { ...utils, router, queryClient }
}

/* ---------- Step 7 API fixtures (shape of the real responses; values are test data, not app data) ---------- */
const Z = '0.00'
export const TOTALS_ZERO = {
  report_count: 0,
  total_sales: Z,
  total_orders: 0,
  collections: {
    cash_received: Z,
    pos_amount: Z,
    bank_transfer: Z,
    link_payment: Z,
    total_received: Z,
  },
  not_yet_received: Z,
  shop_expenses: Z,
  shop_savings: Z,
  shop_expenses_excl_savings: Z,
}
export const MISSING_NOT_CONFIGURED = {
  status: 'not_configured',
  reporting_start: null,
  date_from: null,
  date_to: null,
  expected: 0,
  received: 0,
  missing_count: 0,
  branches: [],
}
export const OWNER_DASHBOARD = {
  mode: 'day',
  date_from: '2026-11-09',
  date_to: '2026-11-09',
  today: '2026-11-09',
  kpis: {
    total_sales: '1500.00',
    total_received: '1400.00',
    not_yet_received: '100.00',
    shop_expenses_excl_savings: '250.00',
    head_office_expenses_excl_savings: '70.00',
    total_savings: '130.00',
    sales_minus_expenses: '1180.00',
    total_orders: 12,
    cash_bank_balance: null,
  },
  balances: {
    status: 'not_configured',
    reporting_start: null,
    balance_date: null,
    cash_in_hand: null,
    enbd: null,
    adcb: null,
    pos_pending: null,
    total: null,
  },
  missing: MISSING_NOT_CONFIGURED,
  alerts: [],
  branches: [
    {
      branch_id: 'b1',
      branch_name: 'Test Branch One',
      report_count: 1,
      total_sales: '1000.00',
      total_orders: 7,
      total_received: '900.00',
      not_yet_received: '100.00',
      shop_expenses_excl_savings: '200.00',
      shop_savings: '100.00',
      head_office_excl_savings: '70.00',
      missing_count: null,
    },
  ],
  unallocated_head_office_excl_savings: Z,
  days: null,
}
export const BRANCH_VIEW_EMPTY = {
  branch_id: null,
  date_from: '2026-11-03',
  date_to: '2026-11-09',
  totals: TOTALS_ZERO,
  reports: [],
  missing: MISSING_NOT_CONFIGURED,
  head_office: null,
  head_office_rows: null,
  head_office_unallocated: null,
}
export const REPORT_SAMPLE = {
  id: 'r1',
  report_date: '2026-11-09',
  branch_id: 'b1',
  branch_name: 'Test Branch One',
  total_sales: '1000.00',
  order_count: 7,
  cash_received: '600.00',
  pos_amount: '200.00',
  bank_transfer: '100.00',
  link_payment: '50.00',
  shop_expenses: '300.00',
  shop_savings: '100.00',
  total_received: '950.00',
  difference: '50.00',
  check: 'Diff',
  shop_expenses_excl_savings: '200.00',
  created_at: '2026-11-09T10:00:00Z',
}
