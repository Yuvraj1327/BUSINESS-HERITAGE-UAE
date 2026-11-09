import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { AuthProvider } from '@/auth/AuthProvider'
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

const OWNER_PERMS = Object.fromEntries(
  [
    'dashboard',
    'branch_management',
    'daily_reports',
    'cash_banks',
    'suppliers',
    'employees',
    'tasks',
    'reports',
    'user_management',
    'settings',
  ].map((m) => [
    m,
    { actions: ['read', 'create', 'update', 'export', 'manage'], scope: 'all_branches' },
  ]),
)
// Mock of what the server sends for a Branch User (matches backend PERMISSION_MATRIX).
const BRANCH_PERMS = {
  dashboard: { actions: ['read'], scope: 'own_branch' },
  branch_management: { actions: ['read'], scope: 'own_branch' },
  daily_reports: { actions: ['create', 'read'], scope: 'own_branch' },
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
