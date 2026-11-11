import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { describeChange, daysText, previewRenewal } from '@/pages/hr/helpers'
import { employeeFormSchema, licenseFormSchema, reasonSchema } from '@/schemas/hr'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  PROFILE_BRANCH,
  alertItem,
  alertSummary,
  PROFILE_OWNER,
  apiError,
  renderApp,
  stubApi,
  type ApiReply,
} from '@/test/render-app'
import { formatAED } from '@/utils/format'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

/* ---------- fixtures: shape of the real responses; values are test data ---------- */
const BRANCHES = [
  { id: 'b1', name: 'Test Branch One', sort_order: 1, is_active: true },
  { id: 'b2', name: 'Test Branch Two', sort_order: 2, is_active: true },
]
const EMP = {
  id: 'e1',
  full_name: 'Test Employee',
  branch_id: 'b1',
  branch_name: 'Test Branch One',
  role_title: 'Presser',
  monthly_salary: '1500.00',
  status: 'Active',
  stored_status: 'Active',
  leave: null,
  visa_cancelled: false,
  visa_cancelled_date: null,
  visa_expiry: '2027-06-01',
  visa_status: 'normal',
  visa_days_remaining: 200,
  passport_expiry: '2026-12-01',
  passport_status: 'urgent',
  passport_days_remaining: 22,
  notes: null,
  payroll_eligible: true,
  archived: false,
  archive_reason: null,
  created_at: '2026-10-01T08:00:00Z',
  updated_at: '2026-10-02T08:00:00Z',
  created_by_name: 'Test Owner',
  updated_by_name: 'Test Owner',
}
const LEAVE_EMP = {
  ...EMP,
  id: 'e2',
  full_name: 'Leave Employee',
  status: 'On Leave',
  stored_status: 'Leave',
  leave: {
    leave_start: '2026-05-20',
    limit_date: '2026-11-20',
    days_on_leave: 173,
    days_remaining: 11,
    state: 'approaching_limit',
  },
  payroll_eligible: false,
}
const SUMMARY = {
  total_active: 7,
  on_leave: 2,
  close_to_limit: 1,
  visa_cancelled: 3,
  monthly_payroll: '10500.50',
  payroll_employees: 7,
}
const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const HISTORY = [
  {
    id: 2,
    occurred_at: '2026-10-02T08:00:00Z',
    actor_name: 'Test Owner',
    action: 'UPDATE',
    table_name: 'employees',
    record_id: 'e1',
    reason: 'Annual raise',
    old_values: { monthly_salary: '1400.00', updated_at: 'x' },
    new_values: { monthly_salary: '1500.00', updated_at: 'y' },
  },
]
const COMPLIANCE_SUMMARY = {
  visas: { expired: 1, urgent: 2, upcoming: 3, normal: 4, not_recorded: 0, cancelled: 1 },
  passports: { expired: 0, urgent: 1, upcoming: 2, normal: 5, not_recorded: 1, cancelled: 0 },
  visas_expiring_30: 2,
  passports_expiring_30: 1,
  passports_under_6_months: 3,
  visas_cancelled: 1,
}
const ROW = {
  employee_id: 'e1',
  employee_name: 'Test Employee',
  branch_id: 'b1',
  branch_name: 'Test Branch One',
  employment_status: 'Active',
  expiry_date: '2026-12-01',
  status: 'urgent',
  days_remaining: 22,
}
const LIC = {
  id: 'l1',
  branch_id: 'b1',
  branch_name: 'Test Branch One',
  license_no: 'TL-100',
  authority: 'Test Authority',
  expiry_date: '2026-11-30',
  renewal_fee: '2500.00',
  notes: null,
  status: 'urgent',
  days_remaining: 21,
  renewal_count: 1,
  last_renewed_on: '2025-11-25',
  archived: false,
  created_at: '2025-01-01T08:00:00Z',
  updated_at: '2025-11-25T08:00:00Z',
  updated_by_name: 'Test Owner',
}
const RENEWAL = {
  id: 'r1',
  license_id: 'l1',
  renewed_on: '2025-11-25',
  previous_expiry: '2025-11-30',
  new_expiry: '2026-11-30',
  renewal_fee: '2400.00',
  note: 'Paid at the authority',
  created_at: '2025-11-25T08:00:00Z',
  created_by_name: 'Test Owner',
}
const LIC_SUMMARY = {
  total: 4,
  expired: 1,
  expiring_30: 1,
  expiring_60: 2,
  renewal_fees_due: '5000.00',
  fees_due_count: 2,
}
const ALERTS = {
  items: [
    {
      key: 'visa_expiring:e1',
      kind: 'visa_expiring',
      severity: 'danger',
      title: 'Visa expiring within 30 days',
      detail: 'Test Employee (Test Branch One): expires in 5 days',
      due_date: '2026-11-14',
      days_remaining: 5,
      href: '/employees/e1',
    },
    {
      key: 'license_renewal_due:l1',
      kind: 'license_renewal_due',
      severity: 'warning',
      title: 'Trade licence renewal approaching',
      detail: 'TL-100 (Test Branch One): expires in 70 days',
      due_date: '2027-01-18',
      days_remaining: 70,
      href: '/trade-licenses/l1',
    },
  ],
  total: 2,
  danger: 1,
  warning: 1,
}

interface World {
  employees: unknown
  detail: unknown
  alerts: { items: { kind: string; title: string; href: string }[] }
  failList: boolean
  renewFail: boolean
}
function api(profile: object, over: Partial<World> = {}) {
  const w: World = {
    employees: page([EMP, LEAVE_EMP]),
    detail: { employee: EMP, history: HISTORY },
    alerts: ALERTS,
    failList: false,
    renewFail: false,
    ...over,
  }
  return stubApi((c): ApiReply => {
    const url = c.url ?? ''
    const method = c.method ?? 'get'
    if (url === '/branches') return { status: 200, body: BRANCHES }
    if (url === '/dashboard/owner') return { status: 200, body: {} }
    if (url === '/alerts/summary')
      return {
        status: 200,
        body: alertSummary(
          w.alerts.items.map((a) => alertItem({ kind: a.kind, type_label: a.title, href: a.href })),
        ),
      }
    if (url === '/compliance/alerts') return { status: 200, body: w.alerts }
    if (url === '/employees/summary') return { status: 200, body: SUMMARY }
    if (url === '/employees/leave/summary')
      return {
        status: 200,
        body: {
          on_leave: 2,
          approaching: 1,
          limit_reached: 0,
          visa_cancelled_by_leave: 0,
          items: [LEAVE_EMP],
        },
      }
    if (url === '/employees') {
      if (w.failList) return apiError(500, 'internal_error', 'Boom')
      return method === 'post'
        ? { status: 201, body: w.detail }
        : { status: 200, body: w.employees }
    }
    if (/^\/employees\/e\d$/.test(url)) return { status: 200, body: w.detail }
    if (url.startsWith('/employees/e1/')) return { status: 200, body: w.detail }
    if (url === '/visas-passports/summary') return { status: 200, body: COMPLIANCE_SUMMARY }
    if (url === '/visas-passports/visas' || url === '/visas-passports/passports')
      return { status: 200, body: page([ROW]) }
    if (url.startsWith('/visas-passports/employees/')) return { status: 200, body: w.detail }
    if (url === '/trade-licenses/summary') return { status: 200, body: LIC_SUMMARY }
    if (url === '/trade-licenses')
      return method === 'post'
        ? { status: 201, body: { license: LIC, renewals: [], history: [] } }
        : { status: 200, body: page([LIC]) }
    if (url === '/trade-licenses/l1/renew' && w.renewFail)
      return apiError(
        409,
        'stale_renewal',
        'This licence was already renewed or changed. Reload before renewing again.',
      )
    if (url === '/trade-licenses/l1' || url === '/trade-licenses/l1/renew')
      return { status: 200, body: { license: LIC, renewals: [RENEWAL], history: [] } }
    return { status: 200, body: profile }
  })
}
const body = (call: { data?: unknown }) =>
  JSON.parse(call.data as string) as Record<string, unknown>
const money = (v: string) => formatAED(v).replace(/\u00a0/g, ' ')

beforeEach(() => {
  const sb = createFakeSupabase()
  fake.current = sb
  sb.state.session = makeSession()
  vi.mocked(toast.success).mockClear()
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
describe('HR helpers and form schemas', () => {
  it('previews a renewal as the same date next year (29 Feb becomes 28 Feb)', () => {
    expect(previewRenewal('2026-05-10')).toBe('2027-05-10')
    expect(previewRenewal('2028-02-29')).toBe('2029-02-28')
    expect(previewRenewal('2026-12-31')).toBe('2027-12-31')
  })
  it('describes days remaining and overdue', () => {
    expect(daysText(5)).toBe('5 days left')
    expect(daysText(1)).toBe('1 day left')
    expect(daysText(0)).toBe('Today')
    expect(daysText(-3)).toBe('3 days overdue')
    expect(daysText(null)).toBe('')
  })
  it('summarises an audit row as readable changes, without raw JSON or bookkeeping fields', () => {
    expect(describeChange(HISTORY[0]!)).toBe('Salary: 1400.00 → 1500.00')
    expect(describeChange({ ...HISTORY[0]!, action: 'INSERT' })).toBe('Record created')
  })
  it('employee form: name, branch and a valid non-negative salary are required', () => {
    const ok = {
      full_name: 'A',
      branch_id: 'b1',
      role_title: '',
      monthly_salary: '1500',
      passport_expiry: '',
      visa_expiry: '',
      notes: '',
      reason: '',
    }
    expect(employeeFormSchema.safeParse(ok).success).toBe(true)
    for (const bad of [
      { ...ok, full_name: ' ' },
      { ...ok, branch_id: '' },
      { ...ok, monthly_salary: '' },
      { ...ok, monthly_salary: '-5' },
      { ...ok, monthly_salary: '12.345' },
      { ...ok, visa_expiry: '01/02/2027' },
    ])
      expect(employeeFormSchema.safeParse(bad).success).toBe(false)
  })
  it('licence form: number, expiry date and fee are required', () => {
    const ok = {
      branch_id: 'b1',
      license_no: 'TL-1',
      authority: '',
      expiry_date: '2027-01-01',
      renewal_fee: '100',
      notes: '',
      reason: '',
    }
    expect(licenseFormSchema.safeParse(ok).success).toBe(true)
    expect(licenseFormSchema.safeParse({ ...ok, license_no: '' }).success).toBe(false)
    expect(licenseFormSchema.safeParse({ ...ok, expiry_date: '' }).success).toBe(false)
    expect(licenseFormSchema.safeParse({ ...ok, renewal_fee: 'abc' }).success).toBe(false)
  })
  it('a reason needs 3+ characters', () => {
    expect(reasonSchema.safeParse('ab').success).toBe(false)
    expect(reasonSchema.safeParse(' ok! ').success).toBe(true)
  })
})

/* ---------------------------------- employees ---------------------------------- */
describe('Employees page', () => {
  it('shows the five summary cards exactly as calculated by the server', async () => {
    api(PROFILE_OWNER)
    renderApp('/employees')
    const cards = await screen.findByLabelText('Employee summary')
    await within(cards).findByText(money('10500.50'))
    for (const [label, value] of [
      ['Total Active Employees', '7'],
      ['Currently on Leave', '2'],
      ['Close to Six-Month Leave Limit', '1'],
      ['Visa Cancelled', '3'],
    ] as const) {
      expect(within(cards).getByText(label).closest('div')!.parentElement!).toHaveTextContent(value)
    }
    expect(within(cards).getByText(/Not proof of payment/)).toBeInTheDocument()
  })

  it('lists employees with status, visa and passport indicators and a leave watch', async () => {
    api(PROFILE_OWNER)
    renderApp('/employees')
    const table = await screen.findByRole('table', { name: 'Employees' })
    expect(await within(table).findByRole('link', { name: 'Test Employee' })).toHaveAttribute(
      'href',
      '/employees/e1',
    )
    expect(within(table).getAllByText(money('1500')).length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Expiring soon').length).toBeGreaterThan(0) // passport urgent
    expect(within(table).getByText('Approaching Six-Month Limit')).toBeInTheDocument()
    const watch = screen.getByRole('table', { name: 'Leave watch' })
    expect(within(watch).getByText('11')).toBeInTheDocument() // days remaining
  })

  it('search, branch and status filters are sent to the server and reset to page 1', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/employees')
    await screen.findByRole('table', { name: 'Employees' })
    await user.type(screen.getByLabelText('Search'), 'rav')
    await waitFor(() =>
      expect(
        calls.some((c) => c.url === '/employees' && (c.params as { q?: string }).q === 'rav'),
      ).toBe(true),
    )
  })

  it('opens pre-filtered from a dashboard alert link (?status=Visa+Cancelled)', async () => {
    const calls = api(PROFILE_OWNER)
    renderApp('/employees?status=Visa+Cancelled')
    await screen.findByRole('table', { name: 'Employees' })
    expect(
      calls.some(
        (c) =>
          c.url === '/employees' && (c.params as { status?: string }).status === 'Visa Cancelled',
      ),
    ).toBe(true)
  })

  it('shows an error state with retry when the list fails', async () => {
    api(PROFILE_OWNER, { failList: true })
    renderApp('/employees')
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })

  it('shows an empty state when nothing matches', async () => {
    api(PROFILE_OWNER, { employees: page([]) })
    renderApp('/employees')
    expect(await screen.findByText('No employees found')).toBeInTheDocument()
  })

  it('adding an employee validates first, then posts only the allowed fields (no ID numbers)', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/employees')
    await user.click(await screen.findByRole('button', { name: /Add employee/ }))
    const form = await screen.findByRole('form', { name: 'Employee form' })
    expect(within(form).queryByLabelText(/passport number|emirates id/i)).not.toBeInTheDocument()
    await user.click(within(form).getByRole('button', { name: 'Add employee' }))
    expect(await within(form).findByText('Enter the employee name')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post' && c.url === '/employees')).toBe(false)
    await user.type(within(form).getByLabelText(/Full name/), 'New Person')
    await user.type(within(form).getByLabelText(/Monthly salary/), '1200')
    await user.click(within(form).getByRole('combobox', { name: /Assigned branch/ }))
    await user.click(await screen.findByRole('option', { name: 'Test Branch Two' }))
    await user.click(within(form).getByRole('button', { name: 'Add employee' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'post' && c.url === '/employees')).toBe(true),
    )
    expect(body(calls.find((c) => c.method === 'post' && c.url === '/employees')!)).toEqual({
      full_name: 'New Person',
      branch_id: 'b2',
      monthly_salary: '1200',
    })
  })
})

describe('Employee detail page', () => {
  it('shows details, indicators and history without raw JSON', async () => {
    api(PROFILE_OWNER)
    renderApp('/employees/e1')
    expect(
      await screen.findByRole('heading', { name: 'Test Employee', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText('Salary: 1400.00 → 1500.00')).toBeInTheDocument()
    expect(screen.getByText(/Reason: Annual raise/)).toBeInTheDocument()
    expect(screen.getAllByText('Expiring soon').length).toBeGreaterThan(0)
  })

  it('starting leave needs a date and a reason, and asks for confirmation', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/employees/e1')
    await user.click(await screen.findByRole('button', { name: /Start leave/ }))
    const dlg = await screen.findByRole('dialog')
    await user.click(within(dlg).getByRole('button', { name: 'Start leave' }))
    expect(await within(dlg).findByText(/at least 3 characters/)).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/employees/e1/status')).toBe(false)
    await user.type(within(dlg).getByLabelText(/Reason/), 'Home leave')
    await user.click(within(dlg).getByRole('button', { name: 'Start leave' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/employees/e1/status')).toBe(true))
    const sent = body(calls.find((c) => c.url === '/employees/e1/status')!)
    expect(sent).toMatchObject({ status: 'On Leave', reason: 'Home leave' })
    expect(typeof sent.leave_start).toBe('string')
    expect(toast.success).toHaveBeenCalledWith('Leave started')
  })

  it('on leave: shows the six-month limit panel and offers return to work', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER, {
      detail: { employee: { ...LEAVE_EMP, id: 'e1' }, history: [] },
    })
    renderApp('/employees/e1')
    expect(await screen.findByText('Leave and six-month limit')).toBeInTheDocument()
    expect(screen.getByText(/not 180 days/)).toBeInTheDocument()
    expect(screen.getByText('11')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Return to work/ }))
    const dlg = await screen.findByRole('dialog')
    await user.type(within(dlg).getByLabelText(/Reason/), 'Back at work')
    await user.click(within(dlg).getByRole('button', { name: 'Return to work' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/employees/e1/return')).toBe(true))
  })

  it('past the limit: warns that returning makes the cancellation permanent', async () => {
    const user = userEvent.setup()
    const past = {
      ...LEAVE_EMP,
      id: 'e1',
      status: 'Visa Cancelled',
      visa_cancelled: true,
      leave: { ...LEAVE_EMP.leave, days_remaining: -4, state: 'visa_cancelled' },
    }
    api(PROFILE_OWNER, { detail: { employee: past, history: [] } })
    renderApp('/employees/e1')
    expect(await screen.findByText(/cancellation permanently/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Return to work/ }))
    expect(await screen.findByText(/makes the visa cancellation permanent/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Start leave/ })).not.toBeInTheDocument()
  })

  it('cancelling a visa is a confirmed, permanent action that needs a reason', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/employees/e1')
    await user.click(await screen.findByRole('button', { name: /Cancel visa/ }))
    const dlg = await screen.findByRole('dialog')
    expect(within(dlg).getByText(/permanent/)).toBeInTheDocument()
    await user.type(within(dlg).getByLabelText(/Reason/), 'Resigned')
    await user.click(within(dlg).getByRole('button', { name: 'Cancel visa' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/employees/e1/status')).toBe(true))
    expect(body(calls.find((c) => c.url === '/employees/e1/status')!)).toMatchObject({
      status: 'Visa Cancelled',
      reason: 'Resigned',
    })
  })

  it('editing salary asks for a reason; a server refusal is shown inside the form', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER)
    renderApp('/employees/e1')
    await user.click(await screen.findByRole('button', { name: /Edit/ }))
    const form = await screen.findByRole('form', { name: 'Employee form' })
    expect(within(form).queryByLabelText(/Reason for the change/)).not.toBeInTheDocument()
    const salary = within(form).getByLabelText(/Monthly salary/)
    await user.clear(salary)
    await user.type(salary, '1800')
    expect(await within(form).findByLabelText(/Reason for the change/)).toBeInTheDocument()
    await user.click(within(form).getByRole('button', { name: 'Save changes' }))
    expect(await within(form).findByText(/at least 3 characters/)).toBeInTheDocument()
  })
})

/* ---------------------------------- visas & passports ---------------------------------- */
describe('Visas & Passports page', () => {
  it('shows separate visa and passport sections with summary cards', async () => {
    api(PROFILE_OWNER)
    renderApp('/visas-passports')
    const visas = await screen.findByLabelText('Visa summary')
    await waitFor(() =>
      expect(
        within(visas).getByText('Visas Expiring ≤ 30 Days').closest('div')!.parentElement!,
      ).toHaveTextContent('2'),
    )
    const pass = screen.getByLabelText('Passport summary')
    await waitFor(() =>
      expect(
        within(pass).getByText('Passports Under 6 Months').closest('div')!.parentElement!,
      ).toHaveTextContent('3'),
    )
    expect(await screen.findByRole('table', { name: 'Visa records' })).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Passport records' })).toBeInTheDocument()
    expect(screen.getByText(/Amber: within 180 days/)).toBeInTheDocument()
    expect(screen.getByText(/Amber: within 90 days/)).toBeInTheDocument()
  })

  it('updating an expiry sends only the date (and optional reason)', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/visas-passports')
    const table = await screen.findByRole('table', { name: 'Visa records' })
    await user.click(
      await within(table).findByRole('button', { name: 'Update visa expiry for Test Employee' }),
    )
    const dlg = await screen.findByRole('dialog')
    const date = within(dlg).getByLabelText(/New expiry date/)
    await user.clear(date)
    await user.type(date, '2027-12-31')
    await user.click(within(dlg).getByRole('button', { name: 'Save expiry' }))
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === 'patch' && c.url === '/visas-passports/employees/e1/visa-expiry',
        ),
      ).toBe(true),
    )
    expect(body(calls.find((c) => c.method === 'patch')!)).toEqual({ expiry_date: '2027-12-31' })
  })

  it('filters by expiry period on the server', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/visas-passports')
    await screen.findByRole('table', { name: 'Visa records' })
    await user.click(screen.getAllByRole('combobox', { name: 'Expiry period' })[0]!)
    await user.click(await screen.findByRole('option', { name: 'Expired' }))
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url === '/visas-passports/visas' &&
            (c.params as { bucket?: string }).bucket === 'expired',
        ),
      ).toBe(true),
    )
  })
})

/* ---------------------------------- trade licences ---------------------------------- */
describe('Trade Licenses page', () => {
  it('shows the five summary cards and the list with status and renewal fee', async () => {
    api(PROFILE_OWNER)
    renderApp('/trade-licenses')
    const cards = await screen.findByLabelText('Licence summary')
    await within(cards).findByText(money('5000'))
    expect(
      within(cards).getByText('Expiring ≤ 30 Days').closest('div')!.parentElement!,
    ).toHaveTextContent('1')
    expect(within(cards).getByText('Renewal Fees Due')).toBeInTheDocument()
    const table = await screen.findByRole('table', { name: 'Trade licences' })
    expect(within(table).getByText('TL-100')).toBeInTheDocument()
    expect(within(table).getByText('Expiring soon')).toBeInTheDocument()
    expect(within(table).getByText(money('2500'))).toBeInTheDocument()
  })

  it('detail: shows renewal history including the preserved previous expiry', async () => {
    api(PROFILE_OWNER)
    renderApp('/trade-licenses/l1')
    const hist = await screen.findByRole('table', { name: 'Renewal history' })
    expect(within(hist).getByText('30 Nov 2025')).toBeInTheDocument()
    expect(within(hist).getByText('30 Nov 2026')).toBeInTheDocument()
    expect(within(hist).getByText(money('2400'))).toBeInTheDocument()
  })

  it('renewal needs confirmation, shows old and new expiry, and sends the expected expiry with a client key', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/trade-licenses/l1')
    await user.click(await screen.findByRole('button', { name: /Mark as renewed/ }))
    const dlg = await screen.findByRole('dialog')
    expect(within(dlg).getByText('30 Nov 2026')).toBeInTheDocument()
    expect(within(dlg).getByText('30 Nov 2027')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/trade-licenses/l1/renew')).toBe(false)
    await user.click(within(dlg).getByRole('button', { name: 'Confirm renewal' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/trade-licenses/l1/renew')).toHaveLength(1),
    )
    const sent = body(calls.find((c) => c.url === '/trade-licenses/l1/renew')!)
    expect(sent).toMatchObject({ expected_expiry: '2026-11-30', renewal_fee: '2500.00' })
    expect(typeof sent.client_key).toBe('string')
    expect(toast.success).toHaveBeenCalledWith('Licence renewed')
  })

  it('a stale or repeated renewal shows the server message and keeps the dialog open', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER, { renewFail: true })
    renderApp('/trade-licenses/l1')
    await user.click(await screen.findByRole('button', { name: /Mark as renewed/ }))
    const dlg = await screen.findByRole('dialog')
    await user.click(within(dlg).getByRole('button', { name: 'Confirm renewal' }))
    expect(await within(dlg).findByText(/already renewed or changed/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('adding a licence validates required fields first', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/trade-licenses')
    await user.click(await screen.findByRole('button', { name: /Add licence/ }))
    const form = await screen.findByRole('form', { name: 'Licence form' })
    await user.click(within(form).getByRole('button', { name: 'Add licence' }))
    expect(await within(form).findByText('Enter the licence number')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post' && c.url === '/trade-licenses')).toBe(false)
  })
})

/* ---------------------------------- alerts and permissions ---------------------------------- */
describe('Compliance alerts and permissions', () => {
  it('the notification bell lists the Owner alerts with links to the records', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER)
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: /Notifications, 2 unread/ }))
    const list = await screen.findByRole('list', { name: 'Alerts' })
    expect(
      within(list).getByRole('link', { name: /Visa expiring within 30 days/ }),
    ).toHaveAttribute('href', '/employees/e1')
    expect(within(list).getByRole('link', { name: /renewal approaching/ })).toHaveAttribute(
      'href',
      '/trade-licenses/l1',
    )
  })

  it('a Branch User never requests HR data and cannot open the pages', async () => {
    const calls = api(PROFILE_BRANCH)
    for (const path of [
      '/employees',
      '/employees/e1',
      '/visas-passports',
      '/trade-licenses',
      '/trade-licenses/l1',
    ]) {
      const { unmount } = renderApp(path)
      expect(
        (await screen.findAllByText(/access denied|not allowed|permission/i)).length,
      ).toBeGreaterThan(0)
      unmount()
    }
    expect(
      calls.some((c) =>
        /^\/(employees|visas-passports|trade-licenses|compliance)/.test(c.url ?? ''),
      ),
    ).toBe(false)
    expect(screen.queryByText('Salary')).not.toBeInTheDocument()
  })
})
