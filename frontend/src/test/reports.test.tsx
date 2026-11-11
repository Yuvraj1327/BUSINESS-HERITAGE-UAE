import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  BRANCH_VIEW_EMPTY,
  OWNER_DASHBOARD,
  PROFILE_BRANCH,
  PROFILE_OWNER,
  REPORT_SAMPLE,
  apiError,
  renderApp,
  stubApi,
  type ApiReply,
} from '@/test/render-app'
import { reportFormSchema } from '@/schemas/reports'
import { addDays, addMonths, quickRange } from '@/utils/period'
import { dubaiToday } from '@/utils/format'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const BRANCHES = [
  { id: 'b1', name: 'Test Branch One', sort_order: 1, is_active: true },
  { id: 'b2', name: 'Test Branch Two', sort_order: 2, is_active: true },
]
const PAGE = { items: [REPORT_SAMPLE], total: 1, page: 1, page_size: 25 }

type Handler = (
  url: string,
  config: { method?: string; data?: unknown; params?: unknown },
) => ApiReply | undefined
function api(profile: object, extra?: Handler) {
  return stubApi((c) => {
    const hit = extra?.(c.url ?? '', c)
    if (hit) return hit
    switch (c.url) {
      case '/branches':
        return { status: 200, body: BRANCHES }
      case '/dashboard/owner':
        return { status: 200, body: OWNER_DASHBOARD }
      case '/branch-date-view':
        return { status: 200, body: BRANCH_VIEW_EMPTY }
      case '/daily-reports':
        return { status: 200, body: PAGE }
      default:
        return { status: 200, body: profile }
    }
  })
}

beforeEach(() => {
  const sb = createFakeSupabase()
  fake.current = sb
  sb.state.session = makeSession()
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
  window.matchMedia ??= (() => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  })) as never
})

/* ---------------------------------- pure rules ---------------------------------- */
describe('report form schema (mirrors the server rules)', () => {
  const today = '2026-11-09'
  const schema = reportFormSchema({ needsBranch: false, today })
  const ok = {
    report_date: today,
    branch_id: '',
    total_sales: '1000',
    order_count: '5',
    cash_received: '',
    pos_amount: '',
    bank_transfer: '',
    link_payment: '',
    shop_expenses: '',
    shop_savings: '',
  }
  const messages = (v: object) => {
    const r = schema.safeParse({ ...ok, ...v })
    return r.success ? [] : r.error.issues.map((i) => i.message)
  }

  it('accepts a valid report and treats blank optional amounts as zero', () => {
    const r = schema.safeParse(ok)
    expect(r.success && r.data.cash_received).toBe('0')
  })
  it.each([
    [{ total_sales: '0' }, 'Total sales must be greater than zero'],
    [{ total_sales: '' }, 'Enter the total sales'],
    [{ cash_received: '-5' }, 'Enter a valid amount (max 2 decimals)'],
    [{ pos_amount: '1.234' }, 'Enter a valid amount (max 2 decimals)'],
    [{ shop_expenses: '10', shop_savings: '20' }, 'Savings cannot exceed shop expenses'],
    [{ report_date: '2026-11-10' }, 'Report date cannot be in the future'],
    [{ order_count: '' }, 'Enter the number of orders'],
    [{ order_count: '1.5' }, 'Enter a whole number of orders (0 or more)'],
  ])('rejects %j', (over, message) => {
    expect(messages(over)).toContain(message)
  })
  it('requires a branch only for users who choose one', () => {
    const owner = reportFormSchema({ needsBranch: true, today })
    const r = owner.safeParse(ok)
    expect(!r.success && r.error.issues.map((i) => i.message)).toContain('Select a branch')
  })
})

describe('period helpers', () => {
  it('moves days and months without time-zone drift', () => {
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(addMonths('2026-01', -1)).toBe('2025-12')
    expect(addMonths('2026-12', 1)).toBe('2027-01')
  })
  it('quick ranges end today in Dubai', () => {
    expect(quickRange('today', '2026-11-09')).toEqual({ from: '2026-11-09', to: '2026-11-09' })
    expect(quickRange('yesterday', '2026-11-09')).toEqual({ from: '2026-11-08', to: '2026-11-08' })
    expect(quickRange('last7', '2026-11-09')).toEqual({ from: '2026-11-03', to: '2026-11-09' })
    expect(quickRange('last14', '2026-11-09')).toEqual({ from: '2026-10-27', to: '2026-11-09' })
  })
})

/* ---------------------------------- Daily Reports ---------------------------------- */
async function fillValid(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/Total Sales/), '1000')
  await user.type(screen.getByLabelText(/Number of Orders/), '10')
  await user.type(screen.getByLabelText(/^Cash/), '600')
  await user.type(screen.getByLabelText(/^POS/), '200')
  await user.type(screen.getByLabelText(/Shop Expenses/), '300')
  await user.type(screen.getByLabelText(/^Savings/), '100')
}

describe('Daily Reports page', () => {
  it('branch user: branch is fixed, date defaults to Dubai today, no future date allowed', async () => {
    api(PROFILE_BRANCH)
    renderApp('/daily-reports')
    await screen.findByRole('form', { name: 'Daily report form' })
    expect(screen.getByTestId('fixed-branch')).toHaveTextContent('SATWA')
    expect(screen.queryByRole('combobox', { name: /Branch/ })).not.toBeInTheDocument()
    const date = screen.getByLabelText(/Report Date/)
    expect(date).toHaveValue(dubaiToday())
    expect(date).toHaveAttribute('max', dubaiToday())
  })

  it('shows validation messages and sends nothing when the form is invalid', async () => {
    const calls = api(PROFILE_BRANCH)
    renderApp('/daily-reports')
    const user = userEvent.setup()
    await screen.findByRole('form', { name: 'Daily report form' })
    await user.click(screen.getByRole('button', { name: 'Review & submit' }))
    expect(await screen.findByText('Enter the total sales')).toBeInTheDocument()
    expect(screen.getByText('Enter the number of orders')).toBeInTheDocument()
    await user.type(screen.getByLabelText(/Total Sales/), '100')
    await user.type(screen.getByLabelText(/Number of Orders/), '1')
    await user.type(screen.getByLabelText(/Shop Expenses/), '10')
    await user.type(screen.getByLabelText(/^Savings/), '20')
    await user.click(screen.getByRole('button', { name: 'Review & submit' }))
    expect(await screen.findByText('Savings cannot exceed shop expenses')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post')).toBe(false)
  })

  it('asks for confirmation, submits without a branch id, shows the server reconciliation, and refreshes data', async () => {
    const calls = api(PROFILE_BRANCH, (url, c) =>
      url === '/daily-reports' && c.method === 'post'
        ? { status: 201, body: REPORT_SAMPLE }
        : undefined,
    )
    const { queryClient } = renderApp('/daily-reports')
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const user = userEvent.setup()
    await screen.findByRole('form', { name: 'Daily report form' })
    await fillValid(user)
    await user.click(screen.getByRole('button', { name: 'Review & submit' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(calls.some((c) => c.method === 'post')).toBe(false) // nothing sent before confirming
    await user.click(within(dialog).getByRole('button', { name: 'Submit report' }))
    const summary = await screen.findByTestId('submitted-summary')
    expect(summary).toHaveTextContent('950.00') // total collections, from the server response
    expect(summary).toHaveTextContent('50.00') // difference
    expect(summary).toHaveTextContent('Diff')
    const post = calls.find((c) => c.method === 'post')!
    const body = JSON.parse(post.data as string)
    expect(body).not.toHaveProperty('branch_id')
    expect(body).toMatchObject({
      total_sales: '1000',
      order_count: 10,
      cash_received: '600',
      shop_savings: '100',
    })
    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: string[] }).queryKey[0])
    expect(keys).toEqual(expect.arrayContaining(['daily-reports', 'dashboard', 'branch-date-view']))
  })

  it('maps a server duplicate error back to the form', async () => {
    api(PROFILE_BRANCH, (url, c) =>
      url === '/daily-reports' && c.method === 'post'
        ? {
            status: 409,
            body: {
              error: {
                code: 'duplicate_report',
                message: 'A report for this branch and date already exists',
                fields: { report_date: ['A report for this branch and date already exists'] },
              },
              request_id: 'r',
            },
          }
        : undefined,
    )
    renderApp('/daily-reports')
    const user = userEvent.setup()
    await screen.findByRole('form', { name: 'Daily report form' })
    await fillValid(user)
    await user.click(screen.getByRole('button', { name: 'Review & submit' }))
    await user.click(await screen.findByRole('button', { name: 'Submit report' }))
    expect(
      (await screen.findAllByText('A report for this branch and date already exists')).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByTestId('submitted-summary')).not.toBeInTheDocument()
  })

  it('owner must choose a branch; branch id is sent', async () => {
    const calls = api(PROFILE_OWNER, (url, c) =>
      url === '/daily-reports' && c.method === 'post'
        ? { status: 201, body: REPORT_SAMPLE }
        : undefined,
    )
    renderApp('/daily-reports')
    const user = userEvent.setup()
    await screen.findByRole('form', { name: 'Daily report form' })
    await fillValid(user)
    await user.click(screen.getByRole('button', { name: 'Review & submit' }))
    expect(await screen.findByText('Select a branch')).toBeInTheDocument()
    const form = screen.getByRole('form', { name: 'Daily report form' })
    await user.click(within(form).getByRole('combobox', { name: /Branch/ }))
    await user.click(await screen.findByRole('option', { name: 'Test Branch Two' }))
    await user.click(screen.getByRole('button', { name: 'Review & submit' }))
    await user.click(await screen.findByRole('button', { name: 'Submit report' }))
    await screen.findByTestId('submitted-summary')
    expect(JSON.parse(calls.find((c) => c.method === 'post')!.data as string).branch_id).toBe('b2')
  })

  it('history: shows reports with Total Collections and Difference, and a branch user has no Void action', async () => {
    api(PROFILE_BRANCH)
    renderApp('/daily-reports')
    const table = await screen.findByRole('table', { name: 'Daily report history' })
    expect(within(table).getByText('Total Collections')).toBeInTheDocument()
    expect(await within(table).findByText('Diff')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Void report/ })).not.toBeInTheDocument()
  })

  it('history: owner can void with a required reason', async () => {
    const calls = api(PROFILE_OWNER, (url, c) =>
      url.endsWith('/void') && c.method === 'post' ? { status: 204, body: null } : undefined,
    )
    renderApp('/daily-reports')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Void report/ }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Void report' }))
    expect(await within(dialog).findByText(/Enter a reason/)).toBeInTheDocument()
    await user.type(within(dialog).getByRole('textbox'), 'Wrong amounts')
    await user.click(within(dialog).getByRole('button', { name: 'Void report' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/daily-reports/r1/void')).toBe(true))
    expect(
      JSON.parse(calls.find((c) => c.url === '/daily-reports/r1/void')!.data as string),
    ).toEqual({
      reason: 'Wrong amounts',
    })
  })

  it('history: empty and error states, and server-side paging parameters', async () => {
    api(PROFILE_BRANCH, (url) =>
      url === '/daily-reports'
        ? { status: 200, body: { items: [], total: 0, page: 1, page_size: 25 } }
        : undefined,
    )
    const first = renderApp('/daily-reports')
    expect(await screen.findByText('No reports found')).toBeInTheDocument()
    first.unmount()

    const calls = api(PROFILE_BRANCH, (url) =>
      url === '/daily-reports' ? { status: 200, body: { ...PAGE, total: 60 } } : undefined,
    )
    renderApp('/daily-reports')
    const user = userEvent.setup()
    await screen.findByText(/Page 1 of 3/)
    await user.click(screen.getByRole('button', { name: /Next/ }))
    await screen.findByText(/Page 1 of 3|Page 2 of 3/)
    await waitFor(() =>
      expect(calls.some((c) => (c.params as { page?: number } | undefined)?.page === 2)).toBe(true),
    )
    expect(
      (calls.find((c) => c.url === '/daily-reports')!.params as { page_size: number }).page_size,
    ).toBe(25)
  })

  it('history shows an error state when the API fails', async () => {
    api(PROFILE_BRANCH, (url) =>
      url === '/daily-reports' ? apiError(500, 'internal_error', 'Server broke') : undefined,
    )
    renderApp('/daily-reports')
    expect((await screen.findAllByText(/Server broke|went wrong/i)).length).toBeGreaterThan(0)
  })

  it('a user without the create permission sees history but no form', async () => {
    api({
      ...PROFILE_BRANCH,
      permissions: {
        dashboard: { actions: ['read'], scope: 'own_branch' },
        daily_reports: { actions: ['read'], scope: 'own_branch' },
      },
    })
    renderApp('/daily-reports')
    await screen.findByRole('table', { name: 'Daily report history' })
    expect(screen.queryByRole('form', { name: 'Daily report form' })).not.toBeInTheDocument()
  })
})

/* ---------------------------------- Owner dashboard ---------------------------------- */
describe('Owner dashboard', () => {
  it('shows all eight KPIs from the API, the branch table, and not-configured balances', async () => {
    api(PROFILE_OWNER)
    renderApp('/')
    const kpis = await screen.findByTestId('kpis')
    await within(kpis).findByText(/1,500\.00/)
    for (const label of [
      'Total Sales',
      'Total Received',
      'Shop Expenses (excl. savings)',
      'Head Office Expenses (excl. savings)',
      'Total Savings',
      'Sales Minus Expenses',
      'Total Orders',
      'Cash + Bank Balance',
    ]) {
      expect(within(kpis).getByText(label)).toBeInTheDocument()
    }
    expect(within(kpis).getByText(/1,180\.00/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Branch-wise summary' })).toBeInTheDocument()
    expect(
      screen.getByText(/Not configured: balances need the opening balances/),
    ).toBeInTheDocument()
  })

  it('empty database: every KPI is zero, nothing is invented, and empty states are shown', async () => {
    const Z = '0.00'
    const empty = {
      ...OWNER_DASHBOARD,
      kpis: {
        total_sales: Z,
        total_received: Z,
        not_yet_received: Z,
        shop_expenses_excl_savings: Z,
        head_office_expenses_excl_savings: Z,
        total_savings: Z,
        sales_minus_expenses: Z,
        total_orders: 0,
        cash_bank_balance: null,
      },
      branches: OWNER_DASHBOARD.branches.map((b) => ({
        ...b,
        report_count: 0,
        total_sales: Z,
        total_orders: 0,
        total_received: Z,
        not_yet_received: Z,
        shop_expenses_excl_savings: Z,
        shop_savings: Z,
        head_office_excl_savings: Z,
      })),
    }
    api(PROFILE_OWNER, (url) =>
      url === '/dashboard/owner' ? { status: 200, body: empty } : undefined,
    )
    renderApp('/')
    const kpis = await screen.findByTestId('kpis')
    await within(kpis).findAllByText(/0\.00/)
    // No non-zero money figure anywhere in the KPI grid.
    expect(kpis.textContent).not.toMatch(/[1-9][\d,]*\.\d{2}/)
    expect(screen.getByText('No sales recorded for this period.')).toBeInTheDocument()
  })

  it('daily/monthly toggle and period navigation change the request', async () => {
    const calls = api(PROFILE_OWNER)
    renderApp('/')
    const user = userEvent.setup()
    await screen.findByTestId('kpis')
    const dashCalls = () =>
      calls
        .filter((c) => c.url === '/dashboard/owner')
        .map((c) => c.params as Record<string, string>)
    await waitFor(() => expect(dashCalls()[0]).toMatchObject({ mode: 'day', date: dubaiToday() }))
    await user.click(screen.getByRole('button', { name: /^Previous$/ }))
    await waitFor(() =>
      expect(dashCalls().at(-1)).toMatchObject({ mode: 'day', date: addDays(dubaiToday(), -1) }),
    )
    await user.click(screen.getByRole('button', { name: 'Monthly' }))
    await waitFor(() =>
      expect(dashCalls().at(-1)).toMatchObject({ mode: 'month', month: dubaiToday().slice(0, 7) }),
    )
    expect(screen.getByRole('button', { name: 'This Month' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Next Month/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /Previous Month/ }))
    await waitFor(() =>
      expect(dashCalls().at(-1)?.month).toBe(addMonths(dubaiToday().slice(0, 7), -1)),
    )
  })

  it('Next is disabled on today (no future dates)', async () => {
    api(PROFILE_OWNER)
    renderApp('/')
    expect(await screen.findByRole('button', { name: /^Next$/ })).toBeDisabled()
  })

  it('shows an error state with retry', async () => {
    let fail = true
    const calls = api(PROFILE_OWNER, (url) =>
      url === '/dashboard/owner' && fail
        ? apiError(500, 'internal_error', 'Dashboard failed')
        : undefined,
    )
    renderApp('/')
    const user = userEvent.setup()
    expect((await screen.findAllByText(/Dashboard failed|went wrong/i)).length).toBeGreaterThan(0)
    fail = false
    await user.click(screen.getByRole('button', { name: /try again|retry/i }))
    await screen.findByTestId('kpis')
    await within(screen.getByTestId('kpis')).findByText(/1,500\.00/)
    expect(calls.filter((c) => c.url === '/dashboard/owner').length).toBeGreaterThan(1)
  })

  it('lists missing reports and other alerts when the API reports them', async () => {
    api(PROFILE_OWNER, (url) =>
      url === '/dashboard/owner'
        ? {
            status: 200,
            body: {
              ...OWNER_DASHBOARD,
              missing: {
                status: 'ok',
                reporting_start: '2026-11-01',
                date_from: '2026-11-09',
                date_to: '2026-11-09',
                expected: 10,
                received: 9,
                missing_count: 1,
                branches: [
                  {
                    branch_id: 'b2',
                    branch_name: 'Test Branch Two',
                    missing_count: 1,
                    dates: ['2026-11-09'],
                  },
                ],
              },
              alerts: [
                {
                  key: 'visas_30',
                  title: 'Visas expiring within 30 days',
                  count: 2,
                  detail: null,
                  severity: 'warning',
                },
              ],
            },
          }
        : undefined,
    )
    renderApp('/')
    expect(await screen.findByText(/of 10 expected reports are/)).toBeInTheDocument()
    expect(
      screen.getByText('Test Branch Two', { selector: 'span.font-medium' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Visas expiring within 30 days')).toBeInTheDocument()
  })

  it('a branch user never requests the owner dashboard', async () => {
    const calls = api(PROFILE_BRANCH)
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard', level: 1 })
    await screen.findByText('Recent reports')
    expect(calls.some((c) => c.url === '/dashboard/owner')).toBe(false)
  })
})

/* ---------------------------------- Branch & Date View ---------------------------------- */
describe('Branch & Date View', () => {
  it('owner: branch filter, quick filters and range validation', async () => {
    const calls = api(PROFILE_OWNER)
    renderApp('/branch-date-view')
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Branch & Date View', level: 1 })
    const viewCalls = () =>
      calls
        .filter((c) => c.url === '/branch-date-view')
        .map((c) => c.params as Record<string, string>)
    await waitFor(() =>
      expect(viewCalls()[0]).toEqual({
        date_from: addDays(dubaiToday(), -6),
        date_to: dubaiToday(),
      }),
    )

    await user.click(screen.getByRole('button', { name: 'Yesterday' }))
    const y = addDays(dubaiToday(), -1)
    await waitFor(() => expect(viewCalls().at(-1)).toMatchObject({ date_from: y, date_to: y }))
    await user.click(screen.getByRole('button', { name: 'Last 14 days' }))
    await waitFor(() =>
      expect(viewCalls().at(-1)).toMatchObject({ date_from: addDays(dubaiToday(), -13) }),
    )

    await user.click(screen.getAllByRole('combobox', { name: 'Branch' }).at(-1)!)
    await user.click(await screen.findByRole('option', { name: 'Test Branch Two' }))
    await waitFor(() => expect(viewCalls().at(-1)).toMatchObject({ branch_id: 'b2' }))

    const before = viewCalls().length
    const from = screen.getByLabelText('From')
    await user.clear(from)
    await user.type(from, '2020-01-01')
    expect(await screen.findByText(/Choose at most 92 days/)).toBeInTheDocument()
    expect(viewCalls().length).toBe(before) // invalid range: no request
  })

  it('shows empty and no-data states, plus the collection breakdown', async () => {
    api(PROFILE_OWNER)
    renderApp('/branch-date-view')
    expect(await screen.findByText('No reports in this range')).toBeInTheDocument()
    const breakdown = screen.getByTestId('collection-breakdown')
    for (const l of ['Cash', 'POS', 'Bank Transfers', 'Payment Links']) {
      expect(within(breakdown).getByText(l)).toBeInTheDocument()
    }
    expect(screen.getByText(/Reporting start date not configured/)).toBeInTheDocument()
  })

  it('shows reports and head-office summary to the owner', async () => {
    api(PROFILE_OWNER, (url) =>
      url === '/branch-date-view'
        ? {
            status: 200,
            body: {
              ...BRANCH_VIEW_EMPTY,
              reports: [REPORT_SAMPLE],
              head_office: { total: '100.00', savings: '30.00', excl_savings: '70.00', count: 2 },
              head_office_rows: [],
              head_office_unallocated: null,
            },
          }
        : undefined,
    )
    renderApp('/branch-date-view')
    expect(await screen.findByText('Head Office expenses')).toBeInTheDocument()
    expect(
      screen.getByRole('table', { name: 'Daily reports in the selected range' }),
    ).toBeInTheDocument()
  })

  it('branch user: no branch filter, never sends a branch id, no head-office section', async () => {
    const calls = api(PROFILE_BRANCH)
    renderApp('/branch-date-view')
    await screen.findByRole('heading', { name: 'Branch & Date View', level: 1 })
    expect(screen.queryByRole('combobox', { name: 'Branch' })).not.toBeInTheDocument()
    await screen.findByText('No reports in this range')
    expect(
      calls
        .filter((c) => c.url === '/branch-date-view')
        .every((c) => !('branch_id' in (c.params as object))),
    ).toBe(true)
    expect(screen.queryByText('Head Office expenses')).not.toBeInTheDocument()
  })

  it('shows an error state when the API refuses', async () => {
    api(PROFILE_BRANCH, (url) =>
      url === '/branch-date-view'
        ? apiError(422, 'validation_error', 'Choose at most 92 days')
        : undefined,
    )
    renderApp('/branch-date-view')
    expect(await screen.findByText(/Choose at most 92 days/)).toBeInTheDocument()
  })
})
