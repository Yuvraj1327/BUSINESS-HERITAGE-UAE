import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defaultEndDate, describeChange, dueText, endText } from '@/pages/rentals/helpers'
import { agreementFormSchema } from '@/schemas/rentals'
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
const cheque = (over: Record<string, unknown> = {}) => ({
  id: 'c1',
  agreement_id: 'a1',
  branch_id: 'b1',
  branch_name: 'Test Branch One',
  landlord: 'Test Landlord LLC',
  unit: 'Shop 12',
  cheque_no: '000100',
  cheque_date: '2026-12-01',
  amount: '3000.00',
  bank: 'ENBD',
  status: 'Pending',
  cleared_on: null,
  bounced_on: null,
  notes: null,
  replaces_id: null,
  replaces_no: null,
  replaced_by_id: null,
  replaced_by_no: null,
  superseded: false,
  timing: 'later',
  days_to_due: 21,
  affects_balance: false,
  created_at: '2026-10-01T08:00:00Z',
  updated_at: '2026-10-01T08:00:00Z',
  cleared_by_name: null,
  bounced_by_name: null,
  ...over,
})
const C_PENDING = cheque()
const C_OVERDUE = cheque({
  id: 'c0',
  cheque_no: '000099',
  cheque_date: '2026-11-01',
  timing: 'overdue',
  days_to_due: -9,
})
const C_CLEARED = cheque({
  id: 'c2',
  cheque_no: '000101',
  status: 'Cleared',
  cleared_on: '2026-11-05',
  timing: 'done',
  days_to_due: null,
  affects_balance: true,
  cleared_by_name: 'Test Owner',
})
const C_BOUNCED = cheque({
  id: 'c3',
  cheque_no: '000102',
  status: 'Bounced',
  bounced_on: '2026-11-06',
  timing: 'done',
  days_to_due: null,
})
const AGREEMENT = {
  id: 'a1',
  branch_id: 'b1',
  branch_name: 'Test Branch One',
  landlord: 'Test Landlord LLC',
  unit: 'Shop 12',
  start_date: '2026-03-01',
  end_date: '2027-02-28',
  annual_rent: '12000.00',
  bank: 'ENBD',
  cheque_count: 4,
  first_cheque_date: '2026-03-01',
  first_cheque_no: '000100',
  notes: null,
  stored_status: 'Active',
  status: 'Active',
  days_to_end: 110,
  renewed_from_id: null,
  renewed_to_id: null,
  live_cheques: 4,
  schedule_total: '12000.00',
  pending_count: 2,
  cleared_count: 1,
  bounced_count: 1,
  next_cheque_date: '2026-12-01',
  created_at: '2026-03-01T08:00:00Z',
  updated_at: '2026-03-01T08:00:00Z',
  created_by_name: 'Test Owner',
  updated_by_name: null,
}
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const CHEQUE_SUMMARY = {
  pending_count: 7,
  due_30_count: 3,
  overdue_count: 2,
  cleared_count: 11,
  bounced_count: 1,
  pending_amount: '21000.00',
  bounced_amount: '3000.00',
  bounced_unresolved_count: 1,
  bounced_unresolved_amount: '3000.00',
  next_cheque: C_PENDING,
}
const RENTAL_SUMMARY = {
  agreements_active: 4,
  expiring_30: 1,
  expired_unrenewed: 0,
  renewal_approaching: 2,
  annual_rent_active: '96000.00',
  cheques: CHEQUE_SUMMARY,
}
const SCHEDULE = {
  agreement_id: 'a1',
  annual_rent: '12000.00',
  total_cheque_value: '12000.00',
  cheque_count: 4,
  matches: true,
  pending: 2,
  cleared: 1,
  bounced: 1,
  items: [
    C_CLEARED,
    C_BOUNCED,
    C_PENDING,
    cheque({ id: 'c4', cheque_no: '000103', cheque_date: '2027-02-01' }),
  ],
}
const DETAIL = {
  agreement: AGREEMENT,
  schedule: SCHEDULE,
  renewals: [
    {
      id: 'a1',
      relation: 'current',
      start_date: '2026-03-01',
      end_date: '2027-02-28',
      annual_rent: '12000.00',
      cheque_count: 4,
      status: 'Active',
    },
  ],
  history: [],
}
const PREVIEW = {
  lines: [
    {
      seq: 0,
      cheque_no: '000200',
      cheque_date: '2026-12-01',
      amount: '3000.00',
      bank: 'ENBD',
      status: 'Pending',
    },
    {
      seq: 1,
      cheque_no: '000201',
      cheque_date: '2027-03-01',
      amount: '3000.00',
      bank: 'ENBD',
      status: 'Pending',
    },
    {
      seq: 2,
      cheque_no: '000202',
      cheque_date: '2027-06-01',
      amount: '3000.00',
      bank: 'ENBD',
      status: 'Pending',
    },
    {
      seq: 3,
      cheque_no: '000203',
      cheque_date: '2027-09-01',
      amount: '3000.00',
      bank: 'ENBD',
      status: 'Pending',
    },
  ],
  annual_rent: '12000.00',
  total_cheque_value: '12000.00',
  cheque_count: 4,
  matches: true,
  end_date: null,
}
const RENEWAL_PREVIEW = {
  old: AGREEMENT,
  start_date: '2027-03-01',
  end_date: '2028-02-29',
  annual_rent: '13000.00',
  old_annual_rent: '12000.00',
  cheque_count: 4,
  first_cheque_no: '000104',
  first_cheque_date: '2027-03-01',
  bank: 'ENBD',
  old_pending_cheques: 2,
  schedule: {
    ...PREVIEW,
    annual_rent: '13000.00',
    total_cheque_value: '13000.00',
    lines: PREVIEW.lines.map((l, i) => ({
      ...l,
      cheque_no: `00010${4 + i}`,
      amount: i === 3 ? '3250.00' : '3250.00',
    })),
  },
}
interface World {
  cheques: unknown[]
  clearFail: boolean
}
function api(profile: object, over: Partial<World> = {}) {
  const w: World = {
    cheques: [C_OVERDUE, C_PENDING, C_CLEARED, C_BOUNCED],
    clearFail: false,
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
        body: alertSummary([
          alertItem({
            kind: 'cheque_overdue',
            type_label: 'PDC cheque overdue',
            module: 'pdc_cheques',
            severity: 'critical',
            href: '/pdc-cheques/c0',
          }),
        ]),
      }
    if (url === '/rentals/summary') return { status: 200, body: RENTAL_SUMMARY }
    if (url === '/rentals/upcoming-expiries') return { status: 200, body: page([AGREEMENT]) }
    if (url === '/rentals/schedule-preview') return { status: 200, body: PREVIEW }
    if (url === '/rentals')
      return method === 'post'
        ? { status: 201, body: DETAIL }
        : { status: 200, body: page([AGREEMENT]) }
    if (url === '/rentals/a1/renewal-preview') return { status: 200, body: RENEWAL_PREVIEW }
    if (url === '/rentals/a1/renew') return { status: 201, body: DETAIL }
    if (url === '/rentals/a1') return { status: 200, body: DETAIL }
    if (url === '/pdc-cheques/summary') return { status: 200, body: CHEQUE_SUMMARY }
    if (url === '/pdc-cheques') return { status: 200, body: page(w.cheques) }
    if (url === '/pdc-cheques/c1/clear' && w.clearFail)
      return apiError(
        422,
        'insufficient_funds',
        'ENBD does not have enough balance to clear this cheque',
      )
    if (/^\/pdc-cheques\/c\d(\/\w+)?$/.test(url))
      return { status: 200, body: { cheque: C_PENDING, agreement: AGREEMENT, history: [] } }
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
describe('Rental helpers and form schema', () => {
  it('previews the default end date as start + 12 months - 1 day', () => {
    expect(defaultEndDate('2026-03-01')).toBe('2027-02-28')
    expect(defaultEndDate('2026-01-15')).toBe('2027-01-14')
    expect(defaultEndDate('2028-02-29')).toBe('2029-02-27')
  })
  it('describes due and end timing', () => {
    expect(dueText(-3)).toBe('3 days overdue')
    expect(dueText(0)).toBe('Due today')
    expect(dueText(1)).toBe('Due in 1 day')
    expect(endText(-1)).toBe('Ended 1 day ago')
    expect(endText(40)).toBe('40 days left')
  })
  it('summarises an audit row as readable changes', () => {
    const e = {
      id: 1,
      occurred_at: '2026-11-01T00:00:00Z',
      actor_name: 'x',
      action: 'UPDATE',
      table_name: 'pdc_cheques',
      record_id: 'c1',
      reason: null,
      old_values: { status: 'Pending', updated_at: 'a' },
      new_values: { status: 'Cleared', updated_at: 'b' },
    }
    expect(describeChange(e)).toBe('Status: Pending → Cleared')
    expect(describeChange({ ...e, action: 'INSERT' })).toBe('Record created')
  })
  it('agreement form: every required field, 1-12 cheques, rent above zero, end after start', () => {
    const ok = {
      branch_id: 'b1',
      landlord: 'L',
      unit: '',
      start_date: '2026-03-01',
      end_date: '',
      annual_rent: '12000',
      cheque_count: '4',
      first_cheque_date: '2026-03-01',
      first_cheque_no: '000100',
      bank: 'ENBD',
      notes: '',
    }
    expect(agreementFormSchema.safeParse(ok).success).toBe(true)
    for (const bad of [
      { ...ok, branch_id: '' },
      { ...ok, landlord: ' ' },
      { ...ok, annual_rent: '0' },
      { ...ok, annual_rent: '12.345' },
      { ...ok, cheque_count: '0' },
      { ...ok, cheque_count: '13' },
      { ...ok, first_cheque_no: '' },
      { ...ok, bank: 'HSBC' },
      { ...ok, end_date: '2026-03-01' },
    ])
      expect(agreementFormSchema.safeParse(bad).success).toBe(false)
  })
})

/* ---------------------------------- rental agreements ---------------------------------- */
describe('Rental Agreements page', () => {
  it('shows the summary cards and the agreement list from the server', async () => {
    api(PROFILE_OWNER)
    renderApp('/rentals')
    const cards = await screen.findByLabelText('Rental summary')
    await within(cards).findByText(money('96000.00'))
    expect(within(cards).getByText('Active agreements')).toBeInTheDocument()
    const table = await screen.findByRole('table', { name: 'Rental agreements' })
    expect(within(table).getByRole('link', { name: 'Test Branch One' })).toHaveAttribute(
      'href',
      '/rentals/a1',
    )
    expect(within(table).getByText('Test Landlord LLC')).toBeInTheDocument()
    expect(within(table).getByText(money('12000.00'))).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Upcoming expiries' })).toBeInTheDocument()
  })

  it('search and filters are sent to the API', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/rentals')
    await screen.findByRole('table', { name: 'Rental agreements' })
    await user.type(screen.getByRole('searchbox', { name: /Search/ }), 'landlord')
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.url === '/rentals' && (c.params as Record<string, unknown>)?.q === 'landlord',
        ),
      ).toBe(true),
    )
  })

  it('adding validates first, previews the schedule, then confirms exactly the reviewed schedule', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/rentals')
    await user.click(await screen.findByRole('button', { name: /Add agreement/ }))
    const form = await screen.findByRole('form', { name: 'Rental agreement form' })
    await user.click(within(form).getByRole('button', { name: 'Preview schedule' }))
    expect(await within(form).findByText('Choose a branch')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/rentals/schedule-preview')).toBe(false)

    await user.click(within(form).getByRole('combobox', { name: /Branch/ }))
    await user.click(await screen.findByRole('option', { name: 'Test Branch One' }))
    await user.type(within(form).getByLabelText(/Landlord name/), 'Test Landlord LLC')
    await user.type(within(form).getByLabelText(/Start date/), '2026-12-01')
    await user.type(within(form).getByLabelText(/Annual rent/), '12000')
    await user.click(within(form).getByRole('combobox', { name: /Number of cheques/ }))
    await user.click(await screen.findByRole('option', { name: '4' }))
    await user.type(within(form).getByLabelText(/First cheque date/), '2026-12-01')
    await user.type(within(form).getByLabelText(/First cheque number/), '000200')

    await user.click(within(form).getByRole('button', { name: 'Preview schedule' }))
    const table = await within(form).findByRole('table', { name: 'Generated cheque schedule' })
    expect(within(table).getAllByRole('row')).toHaveLength(5) // header + 4 cheques
    expect(within(form).getByText('Total equals the annual rent')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post' && c.url === '/rentals')).toBe(false) // nothing saved yet

    await user.click(within(form).getByRole('button', { name: 'Confirm agreement and schedule' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'post' && c.url === '/rentals')).toBe(true),
    )
    const sent = body(calls.find((c) => c.method === 'post' && c.url === '/rentals')!)
    expect(sent).toMatchObject({
      branch_id: 'b1',
      landlord: 'Test Landlord LLC',
      annual_rent: '12000',
      cheque_count: 4,
    })
    expect((sent.cheques as unknown[]).length).toBe(4)
    expect(toast.success).toHaveBeenCalledWith('Rental agreement saved')
  })

  it('changing a field after the preview requires a new preview', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/rentals')
    await user.click(await screen.findByRole('button', { name: /Add agreement/ }))
    const form = await screen.findByRole('form', { name: 'Rental agreement form' })
    await user.click(within(form).getByRole('combobox', { name: /Branch/ }))
    await user.click(await screen.findByRole('option', { name: 'Test Branch One' }))
    await user.type(within(form).getByLabelText(/Landlord name/), 'L')
    await user.type(within(form).getByLabelText(/Start date/), '2026-12-01')
    await user.type(within(form).getByLabelText(/Annual rent/), '12000')
    await user.click(within(form).getByRole('combobox', { name: /Number of cheques/ }))
    await user.click(await screen.findByRole('option', { name: '4' }))
    await user.type(within(form).getByLabelText(/First cheque date/), '2026-12-01')
    await user.type(within(form).getByLabelText(/First cheque number/), '000200')
    await user.click(within(form).getByRole('button', { name: 'Preview schedule' }))
    await within(form).findByRole('button', { name: 'Confirm agreement and schedule' })
    await user.type(within(form).getByLabelText(/Annual rent/), '0')
    expect(
      await within(form).findByRole('button', { name: 'Preview schedule' }),
    ).toBeInTheDocument()
    expect(within(form).getByText(/Preview the schedule again/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post' && c.url === '/rentals')).toBe(false)
  })
})

describe('Agreement details', () => {
  it('shows the schedule with totals; final cheques have no actions, a bounced one can be replaced', async () => {
    api(PROFILE_OWNER)
    renderApp('/rentals/a1')
    const table = await screen.findByRole('table', { name: 'PDC cheque schedule' })
    const row = (no: string) => within(table).getByText(no).closest('tr')!
    expect(within(row('000101')).queryByRole('button')).not.toBeInTheDocument() // cleared: final
    expect(
      within(row('000102')).getByRole('button', { name: /Replace cheque/ }),
    ).toBeInTheDocument()
    expect(within(row('000100')).getByRole('button', { name: /Mark Cleared/ })).toBeInTheDocument()
    expect(screen.getByText('Total equals the annual rent')).toBeInTheDocument()
    expect(screen.getAllByText(money('12000.00')).length).toBeGreaterThan(0)
  })

  it('renewal shows old and new side by side with the new schedule, then sends the expected end date', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/rentals/a1')
    await user.click(await screen.findByRole('button', { name: /Renew/ }))
    const dlg = await screen.findByRole('dialog')
    await user.type(within(dlg).getByLabelText(/New annual rent/), '13000')
    await user.click(within(dlg).getByRole('button', { name: 'Preview renewal' }))
    expect((await within(dlg).findAllByText('01 Mar 2027')).length).toBeGreaterThan(0)
    expect(within(dlg).getAllByText('29 Feb 2028').length).toBeGreaterThan(0)
    expect(
      within(dlg).getByText(/2 pending cheques on the current agreement stay/),
    ).toBeInTheDocument()
    expect(within(dlg).getByRole('table', { name: 'New cheque schedule' })).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/rentals/a1/renew')).toBe(false)
    await user.click(within(dlg).getByRole('button', { name: 'Confirm renewal' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/rentals/a1/renew')).toBe(true))
    const sent = body(calls.find((c) => c.url === '/rentals/a1/renew')!)
    expect(sent).toMatchObject({
      expected_end_date: '2027-02-28',
      confirm: true,
      annual_rent: '13000',
      first_cheque_no: '000104',
    })
    expect(toast.success).toHaveBeenCalledWith('Agreement renewed')
  })
})

/* ---------------------------------- PDC cheques ---------------------------------- */
describe('PDC Cheques page', () => {
  it('shows the seven summary cards plus the next cheque, and the cheque table', async () => {
    api(PROFILE_OWNER)
    renderApp('/pdc-cheques')
    const cards = await screen.findByLabelText('PDC summary')
    await within(cards).findByText(money('21000.00'))
    for (const label of [
      'Total Pending',
      'Pending Due Within 30 Days',
      'Overdue Pending',
      'Cleared',
      'Bounced',
      'Total Pending Amount',
      'Total Bounced Amount',
      'Next Upcoming Cheque',
    ])
      expect(within(cards).getByText(label)).toBeInTheDocument()
    expect(within(cards).getByText(money('3000.00'))).toBeInTheDocument()
    const table = await screen.findByRole('table', { name: 'PDC cheques' })
    for (const h of [
      'Cheque date',
      'Number',
      'Branch',
      'Landlord',
      'Rental agreement',
      'Bank',
      'Amount',
      'Status',
      'Actions',
    ])
      expect(within(table).getByRole('columnheader', { name: h })).toBeInTheDocument()
    expect(within(table).getByText('Overdue')).toBeInTheDocument()
  })

  it('quick views and filters are sent to the API', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/pdc-cheques?view=overdue')
    await screen.findByRole('table', { name: 'PDC cheques' })
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url === '/pdc-cheques' && (c.params as Record<string, unknown>)?.view === 'overdue',
        ),
      ).toBe(true),
    )
    await user.click(screen.getByRole('button', { name: 'Bounced, not replaced' }))
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url === '/pdc-cheques' &&
            (c.params as Record<string, unknown>)?.view === 'bounced_open',
        ),
      ).toBe(true),
    )
  })

  it('Mark Cleared explains the bank deduction, then posts once and confirms', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/pdc-cheques')
    await screen.findByText('000100')
    const table = screen.getByRole('table', { name: 'PDC cheques' })
    const row = within(table).getByText('000100').closest('tr')!
    await user.click(within(row).getByRole('button', { name: /Mark Cleared/ }))
    const dlg = await screen.findByRole('dialog')
    expect(within(dlg).getByText(/ENBD will be reduced by/)).toBeInTheDocument()
    expect(within(dlg).getByText(money('3000.00'))).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/pdc-cheques/c1/clear')).toBe(false)
    await user.click(within(dlg).getByRole('button', { name: 'Mark Cleared' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/pdc-cheques/c1/clear')).toHaveLength(1),
    )
    expect(toast.success).toHaveBeenCalledWith('Cheque marked as cleared')
  })

  it('a refused clear shows the server message and keeps the dialog open', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER, { clearFail: true })
    renderApp('/pdc-cheques')
    await screen.findByText('000100')
    const table = screen.getByRole('table', { name: 'PDC cheques' })
    await user.click(
      within(within(table).getByText('000100').closest('tr')!).getByRole('button', {
        name: /Mark Cleared/,
      }),
    )
    const dlg = await screen.findByRole('dialog')
    await user.click(within(dlg).getByRole('button', { name: 'Mark Cleared' }))
    expect(await within(dlg).findByText(/does not have enough balance/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('Mark Bounced needs a reason, says there is no deduction, and posts the reason', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/pdc-cheques')
    await screen.findByText('000100')
    const table = screen.getByRole('table', { name: 'PDC cheques' })
    await user.click(
      within(within(table).getByText('000100').closest('tr')!).getByRole('button', {
        name: /Mark Bounced/,
      }),
    )
    const dlg = await screen.findByRole('dialog')
    expect(within(dlg).getByText(/No bank deduction is made/)).toBeInTheDocument()
    await user.click(within(dlg).getByRole('button', { name: 'Mark Bounced' }))
    expect(await within(dlg).findByText(/Enter a reason/)).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/pdc-cheques/c1/bounce')).toBe(false)
    await user.type(within(dlg).getByLabelText(/Reason/), 'Returned by the bank')
    await user.click(within(dlg).getByRole('button', { name: 'Mark Bounced' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/pdc-cheques/c1/bounce')).toBe(true))
    expect(body(calls.find((c) => c.url === '/pdc-cheques/c1/bounce')!)).toMatchObject({
      reason: 'Returned by the bank',
    })
  })

  it('cleared cheques offer no actions at all', async () => {
    api(PROFILE_OWNER)
    renderApp('/pdc-cheques')
    await screen.findByText('000100')
    const table = screen.getByRole('table', { name: 'PDC cheques' })
    const row = within(table).getByText('000101').closest('tr')!
    expect(within(row).queryByRole('button')).not.toBeInTheDocument()
    expect(within(row).getByText('Cleared')).toBeInTheDocument()
  })
})

/* ---------------------------------- alerts and permissions ---------------------------------- */
describe('Rental alerts and permissions', () => {
  it('the notification bell lists rental and PDC alerts with a link to the record', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER)
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: /Notifications, 1 unread/ }))
    const list = await screen.findByRole('list', { name: 'Alerts' })
    expect(within(list).getByRole('link', { name: /PDC cheque overdue/ })).toHaveAttribute(
      'href',
      '/pdc-cheques/c0',
    )
  })

  it('a Branch User never requests rental data and cannot open the pages', async () => {
    const calls = api(PROFILE_BRANCH)
    for (const path of ['/rentals', '/rentals/a1', '/pdc-cheques', '/pdc-cheques/c1']) {
      const { unmount } = renderApp(path)
      expect(
        (await screen.findAllByText(/access denied|not allowed|permission/i)).length,
      ).toBeGreaterThan(0)
      unmount()
    }
    expect(calls.some((c) => /^\/(rentals|pdc-cheques)/.test(c.url ?? ''))).toBe(false)
    expect(screen.queryByText('Annual rent')).not.toBeInTheDocument()
  })
})
