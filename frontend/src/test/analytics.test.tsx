import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cellText } from '@/pages/analytics/cell-format'
import { rangeFor } from '@/pages/analytics/ranges'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  PROFILE_BRANCH,
  PROFILE_OWNER,
  apiError,
  renderApp,
  stubApi,
  type ApiReply,
} from '@/test/render-app'
import { addDays } from '@/utils/period'
import { dubaiToday } from '@/utils/format'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const FILTERS = {
  date_from: '2026-11-01',
  date_to: '2026-11-10',
  period: 'day',
  branch_id: null,
  branch_name: 'All Branches',
}
const CATALOG = [
  { key: 'sales_trend', category: 'Sales', title: 'Sales trend', description: 'Sales per day.' },
  {
    key: 'sales_by_branch',
    category: 'Sales',
    title: 'Sales by branch',
    description: 'Per branch.',
  },
  {
    key: 'ledger',
    category: 'Cash & Banks',
    title: 'Account transaction history',
    description: 'Ledger.',
  },
  { key: 'activity', category: 'Activity', title: 'Activity history', description: 'Audit.' },
]
const OVERVIEW = {
  filters: FILTERS,
  kpis: {
    total_sales: '2300.00',
    total_collections: '2000.00',
    total_orders: 9,
    shop_expenses: '140.00',
    head_office_expenses: '60.00',
    total_savings: '130.00',
    sales_minus_expenses: '2100.00',
    cash_bank_balance: '14500.00',
    not_yet_received: '300.00',
    balance_status: 'ok',
    balance_date: '2026-11-10',
  },
  notes: ['Cash and bank balances are company-wide.'],
  generated_at: '2026-11-10T08:00:00Z',
}
const report = (key: string, over: Record<string, unknown> = {}) => ({
  key,
  title: CATALOG.find((c) => c.key === key)?.title ?? key,
  description: 'About this report.',
  filters: FILTERS,
  columns: [
    { key: 'branch', label: 'Branch', kind: 'text' },
    { key: 'sales', label: 'Sales (AED)', kind: 'money' },
    { key: 'orders', label: 'Orders', kind: 'int' },
  ],
  rows: [
    { branch: 'ALSAFA MAIN', sales: '1800.00', orders: 7 },
    { branch: 'JERNAS', sales: '500.00', orders: 2 },
  ],
  total: 2,
  page: 1,
  page_size: 25,
  summary: [{ label: 'Total sales (AED)', value: '2300.00', kind: 'money' }],
  notes: ['Sales come from submitted daily reports.'],
  generated_at: '2026-11-10T08:00:00Z',
  ...over,
})
const CHARTS = {
  filters: FILTERS,
  generated_at: '2026-11-10T08:00:00Z',
  charts: [
    {
      key: 'sales_trend',
      title: 'Sales trend',
      kind: 'line',
      unit: 'AED',
      series: ['Sales'],
      points: [],
      empty_message: 'No sales reported in this period.',
    },
    {
      key: 'task_status',
      title: 'Task status',
      kind: 'pie',
      unit: 'count',
      series: ['Tasks'],
      points: [],
      empty_message: 'No tasks yet.',
    },
  ],
}

function api(profile: object, opts: { exportFails?: boolean } = {}) {
  return stubApi((c): ApiReply => {
    const url = c.url ?? ''
    if (url === '/branches')
      return { status: 200, body: [{ id: 'b1', name: 'JERNAS', sort_order: 1, is_active: true }] }
    if (url === '/alerts/summary')
      return {
        status: 200,
        body: {
          total_active: 0,
          critical: 0,
          warning: 0,
          info: 0,
          unread: 0,
          acknowledged: 0,
          recent: [],
          by_module: {},
        },
      }
    if (url === '/reports/catalog') return { status: 200, body: CATALOG }
    if (url === '/reports/overview') return { status: 200, body: OVERVIEW }
    if (url === '/reports/charts') return { status: 200, body: CHARTS }
    if (url === '/reports/activity/actors')
      return { status: 200, body: [{ id: 'u1', name: 'Test Owner' }] }
    if (url.endsWith('/export')) {
      if (opts.exportFails) return apiError(500, 'internal_error')
      return { status: 200, body: new Blob(['a,b']) }
    }
    if (url === '/reports/activity')
      return {
        status: 200,
        body: report('activity', {
          columns: [
            { key: 'occurred_at', label: 'Date and time (Dubai)', kind: 'datetime' },
            { key: 'user', label: 'User', kind: 'text' },
            { key: 'summary', label: 'Change', kind: 'text' },
          ],
          rows: [
            {
              occurred_at: '2026-11-10T08:00:00Z',
              user: 'Test Owner',
              summary: 'Status: To Do → Done',
            },
          ],
          total: 1,
          summary: [],
          notes: [],
        }),
      }
    if (url.startsWith('/reports/')) return { status: 200, body: report(url.slice(9)) }
    return { status: 200, body: profile }
  })
}

beforeEach(() => {
  const sb = createFakeSupabase()
  fake.current = sb
  sb.state.session = makeSession()
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
})

describe('quick ranges and cell formatting', () => {
  it('computes Dubai date ranges', () => {
    expect(rangeFor('today', '2026-11-10')).toEqual({ from: '2026-11-10', to: '2026-11-10' })
    expect(rangeFor('yesterday', '2026-11-10')).toEqual({ from: '2026-11-09', to: '2026-11-09' })
    expect(rangeFor('last7', '2026-11-10')).toEqual({ from: '2026-11-04', to: '2026-11-10' })
    expect(rangeFor('last30', '2026-11-10')).toEqual({
      from: '2026-10-12',
      to: '2026-11-10',
    })
    expect(rangeFor('this_month', '2026-11-10')).toEqual({ from: '2026-11-01', to: '2026-11-10' })
    expect(rangeFor('last_month', '2026-11-10')).toEqual({ from: '2026-10-01', to: '2026-10-31' })
    expect(rangeFor('last_month', '2026-01-15')).toEqual({ from: '2025-12-01', to: '2025-12-31' })
    expect(rangeFor('this_year', '2026-11-10')).toEqual({ from: '2026-01-01', to: '2026-11-10' })
  })

  it('formats money, counts and blanks', () => {
    expect(cellText({ key: 'a', label: 'a', kind: 'money' }, '1800.5')).toMatch(/AED/)
    expect(cellText({ key: 'a', label: 'a', kind: 'money' }, '1800.5')).toMatch(/1,800\.50/)
    expect(cellText({ key: 'a', label: 'a', kind: 'int' }, 1200)).toBe('1,200')
    expect(cellText({ key: 'a', label: 'a', kind: 'text' }, null)).toBe('—')
    expect(cellText({ key: 'a', label: 'a', kind: 'pct' }, '12.5')).toBe('12.5%')
  })
})

describe('Reports & Analytics page', () => {
  it('shows the KPI cards, the first report and its totals', async () => {
    const calls = api(PROFILE_OWNER)
    renderApp('/reports')
    expect(
      await screen.findByRole('heading', { name: 'Reports & Analytics', level: 1 }),
    ).toBeInTheDocument()
    const kpis = await screen.findByLabelText('Key figures')
    await waitFor(() => expect(within(kpis).getByText(/2,300\.00/)).toBeInTheDocument())
    for (const label of [
      'Total Sales',
      'Total Collections',
      'Total Orders',
      'Total Shop Expenses',
      'Total Head Office Expenses',
      'Total Savings',
      'Sales Minus Expenses',
      'Cash + Bank Balance',
    ])
      expect(within(kpis).getByText(label)).toBeInTheDocument()
    expect(within(kpis).getByText(/14,500\.00/)).toBeInTheDocument()
    expect(await screen.findByRole('cell', { name: 'ALSAFA MAIN' })).toBeInTheDocument()
    expect(screen.getByLabelText('Report totals')).toHaveTextContent('2,300.00')
    expect(screen.getByText('Sales come from submitted daily reports.')).toBeInTheDocument()
    const today = dubaiToday()
    const ov = calls.find((c) => c.url === '/reports/overview')!
    expect(ov.params).toMatchObject({
      date_from: `${today.slice(0, 7)}-01`,
      date_to: today,
      period: 'day',
    })
    expect(ov.params).not.toHaveProperty('branch_id')
  })

  it('applies a quick range to the KPIs and the report', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/reports')
    await screen.findByRole('cell', { name: 'ALSAFA MAIN' })
    await user.click(screen.getByRole('button', { name: 'Last 7 Days' }))
    const today = dubaiToday()
    await waitFor(() => {
      const last = calls.filter((c) => c.url === '/reports/sales_trend').at(-1)!
      expect(last.params).toMatchObject({ date_from: addDays(today, -6), date_to: today })
    })
    expect(calls.filter((c) => c.url === '/reports/overview').at(-1)!.params).toMatchObject({
      date_from: addDays(today, -6),
    })
    expect(screen.getByRole('button', { name: 'Last 7 Days' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('switches category and sorts by a column', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/reports')
    await screen.findByRole('cell', { name: 'ALSAFA MAIN' })
    await user.click(screen.getByRole('button', { name: 'Sort by Sales (AED)' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/reports/sales_trend').at(-1)!.params).toMatchObject({
        sort: 'sales',
        desc: false,
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Sort by Sales (AED)' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/reports/sales_trend').at(-1)!.params).toMatchObject({
        sort: 'sales',
        desc: true,
      }),
    )
    await user.click(screen.getByRole('tab', { name: 'Cash & Banks' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/reports/ledger')).toBe(true))
    expect(screen.queryByRole('tab', { name: 'Activity' })).not.toBeInTheDocument()
  })

  it('exports CSV and Excel through the server with the current filters', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/reports')
    await screen.findByRole('cell', { name: 'ALSAFA MAIN' })
    await user.click(screen.getByRole('button', { name: /Export CSV/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1))
    const csv = calls.find((c) => c.url === '/reports/sales_trend/export')!
    expect(csv.params).toMatchObject({ format: 'csv', period: 'day' })
    expect(csv.responseType).toBe('blob')
    await user.click(screen.getByRole('button', { name: /Export Excel/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(2))
    expect(
      calls.filter((c) => c.url === '/reports/sales_trend/export').at(-1)!.params,
    ).toMatchObject({ format: 'xlsx' })
  })

  it('reports a failed export without crashing', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER, { exportFails: true })
    renderApp('/reports')
    await screen.findByRole('cell', { name: 'ALSAFA MAIN' })
    await user.click(screen.getByRole('button', { name: /Export CSV/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(screen.getByRole('cell', { name: 'ALSAFA MAIN' })).toBeInTheDocument()
  })

  it('shows chart empty states on the Charts tab', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER)
    renderApp('/reports')
    await screen.findByRole('cell', { name: 'ALSAFA MAIN' })
    await user.click(screen.getByRole('tab', { name: /Charts/ }))
    expect(await screen.findByText('No sales reported in this period.')).toBeInTheDocument()
    expect(screen.getByText('No tasks yet.')).toBeInTheDocument()
  })

  it('shows an empty table message when a report has no rows', async () => {
    stubApi((c): ApiReply => {
      const url = c.url ?? ''
      if (url === '/reports/catalog') return { status: 200, body: CATALOG }
      if (url === '/reports/overview') return { status: 200, body: OVERVIEW }
      if (url === '/reports/sales_trend')
        return {
          status: 200,
          body: report('sales_trend', { rows: [], total: 0, summary: [], notes: [] }),
        }
      if (url === '/branches' || url === '/alerts/summary')
        return {
          status: 200,
          body:
            url === '/branches'
              ? []
              : {
                  total_active: 0,
                  critical: 0,
                  warning: 0,
                  info: 0,
                  unread: 0,
                  acknowledged: 0,
                  recent: [],
                  by_module: {},
                },
        }
      return { status: 200, body: PROFILE_OWNER }
    })
    renderApp('/reports')
    expect(await screen.findByText('No data for these filters')).toBeInTheDocument()
  })

  it('blocks a Branch User from Reports and Activity History', async () => {
    const calls = api(PROFILE_BRANCH)
    for (const path of ['/reports', '/activity-history']) {
      const { unmount } = renderApp(path)
      expect(
        await screen.findByText(/Access denied|do not have access|not allowed/i),
      ).toBeInTheDocument()
      unmount()
    }
    expect(calls.some((c) => (c.url ?? '').startsWith('/reports'))).toBe(false)
    renderApp('/')
    await screen.findByRole('link', { name: 'Dashboard' })
    expect(screen.queryByRole('link', { name: 'Reports & Analytics' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Activity History' })).not.toBeInTheDocument()
  })
})

describe('Activity History page', () => {
  it('lists audit changes and exports with its filters', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/activity-history')
    expect(
      await screen.findByRole('heading', { name: 'Activity History', level: 1 }),
    ).toBeInTheDocument()
    expect(await screen.findByRole('cell', { name: 'Status: To Do → Done' })).toBeInTheDocument()
    const first = calls.find((c) => c.url === '/reports/activity')!
    expect(first.params).toMatchObject({ date_from: addDays(dubaiToday(), -6), page: 1 })
    await user.type(screen.getByLabelText('Record reference'), 'abc')
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/reports/activity').at(-1)!.params).toMatchObject({
        q: 'abc',
      }),
    )
    await user.click(screen.getByRole('button', { name: /Export CSV/ }))
    await waitFor(() => expect(calls.some((c) => c.url === '/reports/activity/export')).toBe(true))
  })
})
