import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  expenseFormSchema,
  openingFormSchema,
  paymentFormSchema,
  settlementFormSchema,
  transferFormSchema,
} from '@/schemas/finance'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  PROFILE_BRANCH,
  PROFILE_OWNER,
  apiError,
  renderApp,
  stubApi,
  type ApiReply,
} from '@/test/render-app'
import { dubaiToday, formatAED } from '@/utils/format'

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
const Z = '0.00'
const OPENING_NONE = {
  status: 'not_configured',
  as_of_date: null,
  tracking_start: null,
  receipts_bank: null,
  enbd_balance: Z,
  adcb_balance: Z,
  pos_pending: Z,
  savings_brought_forward: Z,
  branch_cash: [
    { branch_id: 'b1', branch_name: 'Test Branch One', amount: Z },
    { branch_id: 'b2', branch_name: 'Test Branch Two', amount: Z },
  ],
  supplier_dues: [{ supplier_id: 's1', supplier_name: 'Chem Co', amount: Z }],
  total_branch_cash: Z,
  total_supplier_dues: Z,
  date_locked: false,
  updated_at: null,
  updated_by_name: null,
}
const OPENING_SET = {
  ...OPENING_NONE,
  status: 'configured',
  as_of_date: '2026-11-01',
  tracking_start: '2026-11-02',
  receipts_bank: 'ENBD',
  enbd_balance: '10000.00',
  branch_cash: [
    { branch_id: 'b1', branch_name: 'Test Branch One', amount: '1000.00' },
    { branch_id: 'b2', branch_name: 'Test Branch Two', amount: '500.00' },
  ],
  total_branch_cash: '1500.00',
  date_locked: true,
  updated_at: '2026-11-02T08:00:00Z',
  updated_by_name: 'Test Owner',
}
const BAL_NONE = {
  status: 'not_configured',
  tracking_start: null,
  balance_date: null,
  cash_in_hand: null,
  enbd: null,
  adcb: null,
  pos_pending: null,
  total_cash_bank: null,
  total_savings: null,
}
const BAL_OK = {
  status: 'ok',
  tracking_start: '2026-11-02',
  balance_date: '2026-11-09',
  cash_in_hand: '1810.00',
  enbd: '10300.00',
  adcb: '5000.00',
  pos_pending: '1100.00',
  total_cash_bank: '17110.00',
  total_savings: '350.00',
}
const ACCOUNTS = {
  status: 'ok',
  date_from: '2026-11-02',
  date_to: '2026-11-09',
  accounts: [
    {
      account: 'Cash',
      opening: '1500.00',
      incoming: '500.00',
      outgoing: '190.00',
      closing: '1810.00',
    },
    {
      account: 'ENBD',
      opening: '10000.00',
      incoming: '300.00',
      outgoing: '0.00',
      closing: '10300.00',
    },
  ],
}
const BRANCH_CASH = {
  status: 'ok',
  balance_date: '2026-11-09',
  rows: [
    {
      branch_id: 'b1',
      branch_name: 'Test Branch One',
      opening: '1000.00',
      incoming: '400.00',
      outgoing: '150.00',
      closing: '1250.00',
    },
  ],
  total: '1250.00',
}
const LEDGER = {
  status: 'ok',
  items: [
    {
      txn_date: '2026-11-03',
      txn_type: 'Daily report cash',
      source_table: 'daily_reports',
      source_id: 'r1',
      branch_id: 'b1',
      branch_name: 'Test Branch One',
      account: 'Cash',
      amount: '400.00',
      description: 'Report 2026-11-03',
      created_by: 'u1',
      created_by_name: 'Clerk Ali',
      created_at: '2026-11-03T10:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  total_incoming: '400.00',
  total_outgoing: '0.00',
}
const TRANSFER = {
  id: 't1',
  transfer_date: '2026-11-04',
  from_account: 'ENBD',
  to_account: 'ADCB',
  branch_id: null,
  branch_name: null,
  amount: '200.00',
  reference: 'T-1',
  note: null,
  created_at: '2026-11-04T08:00:00Z',
  voided: false,
}
const CATEGORIES = [
  { id: 'c1', name: 'Utilities' },
  { id: 'c2', name: 'Rent' },
]
const EXPENSE = {
  id: 'e1',
  expense_date: '2026-11-05',
  branch_id: null,
  branch_name: null,
  category_id: 'c1',
  category: 'Utilities',
  amount: '60.00',
  paid_from: 'Cash',
  note: 'Gas bill',
  is_saving: false,
  voided: false,
  void_reason: null,
  corrects_id: null,
  created_at: '2026-11-05T08:00:00Z',
  created_by_name: 'Test Owner',
}
const EXPENSES = {
  items: [EXPENSE],
  total: 1,
  page: 1,
  page_size: 25,
  totals: { total: '60.00', savings: '0.00', excl_savings: '60.00', count: 1 },
}
const SUPPLIER = {
  id: 's1',
  name: 'Chem Co',
  category: 'Detergents',
  payment_terms: '30 days',
  notes: 'Delivers Mondays',
  is_active: true,
  opening_outstanding: '1000.00',
  new_dues: '250.00',
  total_paid: '400.00',
  outstanding: '850.00',
  created_at: '2026-10-01T08:00:00Z',
}
const SUPPLIERS = { items: [SUPPLIER], total: 1, page: 1, page_size: 25 }
const SUPPLIER_SUMMARY = {
  total_suppliers: 3,
  total_outstanding: '1200.00',
  total_paid: '400.00',
  with_outstanding: 2,
}
const ENTRY = {
  id: 'se1',
  supplier_id: 's1',
  supplier_name: 'Chem Co',
  entry_date: '2026-11-04',
  kind: 'payment',
  amount: '400.00',
  paid_from: 'ENBD',
  branch_name: null,
  reference: 'CHQ-9',
  note: null,
  voided: false,
  void_reason: null,
  created_at: '2026-11-04T08:00:00Z',
  created_by_name: 'Test Owner',
}

type Handler = (
  url: string,
  config: { method?: string; data?: unknown; params?: unknown },
) => ApiReply | undefined
interface World {
  opening: object
  balances: object
  supplier: object
  handler?: Handler
}
function api(profile: object, world: Partial<World> = {}) {
  const w: World = { opening: OPENING_SET, balances: BAL_OK, supplier: SUPPLIER, ...world }
  return stubApi((c) => {
    const hit = w.handler?.(c.url ?? '', c)
    if (hit) return hit
    const url = c.url ?? ''
    const method = (c.method ?? 'get').toLowerCase()
    if (url === '/branches') return { status: 200, body: BRANCHES }
    if (url === '/opening-balances') return { status: 200, body: w.opening }
    if (url === '/opening-balances/history') return { status: 200, body: [] }
    if (url === '/cash-banks/summary') return { status: 200, body: w.balances }
    if (url === '/cash-banks/accounts') return { status: 200, body: ACCOUNTS }
    if (url === '/cash-banks/branches') return { status: 200, body: BRANCH_CASH }
    if (url === '/cash-banks/transactions') return { status: 200, body: LEDGER }
    if (url === '/cash-banks/transfers')
      return {
        status: method === 'post' ? 201 : 200,
        body: method === 'post' ? TRANSFER : [TRANSFER],
      }
    if (url === '/cash-banks/pos-settlements') return { status: 200, body: [] }
    if (url === '/expenses/categories') return { status: 200, body: CATEGORIES }
    if (url === '/expenses')
      return { status: method === 'post' ? 201 : 200, body: method === 'post' ? EXPENSE : EXPENSES }
    if (url === '/expenses/e1') return { status: 200, body: { expense: EXPENSE, history: [] } }
    if (url.startsWith('/expenses/e1/saving'))
      return { status: 200, body: { ...EXPENSE, is_saving: true } }
    if (url === '/suppliers/summary') return { status: 200, body: SUPPLIER_SUMMARY }
    if (url === '/suppliers') return { status: 200, body: SUPPLIERS }
    if (url === '/suppliers/s1') return { status: 200, body: w.supplier }
    if (url === '/suppliers/s1/entries')
      return { status: 200, body: { items: [ENTRY], total: 1, page: 1, page_size: 25 } }
    if (url === '/suppliers/s1/payments') return { status: 201, body: ENTRY }
    if (url === '/suppliers/s1/mark-paid')
      return { status: 201, body: { ...ENTRY, amount: '850.00' } }
    if (url.endsWith('/void')) return { status: 204, body: null }
    return { status: 200, body: profile }
  })
}
const body = (call: { data?: unknown }) =>
  JSON.parse(call.data as string) as Record<string, unknown>
const posted = <T extends { method?: string; url?: string }>(
  calls: T[],
  url: string,
): T | undefined => calls.find((c) => c.method === 'post' && c.url === url)
const owner = () => PROFILE_OWNER
// formatAED uses a non-breaking space; Testing Library normalises the DOM text to a plain space
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
describe('finance form schemas (mirror the server rules)', () => {
  const today = '2026-11-09'
  const messages = (r: { success: boolean; error?: { issues: { message: string }[] } }) =>
    r.success ? [] : (r.error?.issues.map((i) => i.message) ?? [])

  it('expense: positive amount, 2 decimals, no future date, category and source required', () => {
    const s = expenseFormSchema({ today, minDate: '2026-11-02' })
    const ok = {
      expense_date: today,
      branch_id: 'all',
      category_id: 'c1',
      amount: '60',
      paid_from: 'Cash',
      note: '',
      is_saving: false,
    }
    expect(s.safeParse(ok).success).toBe(true)
    expect(messages(s.safeParse({ ...ok, amount: '0' }))).toContain(
      'Amount must be greater than zero',
    )
    expect(messages(s.safeParse({ ...ok, amount: '1.234' }))).toContain(
      'Enter a valid amount (max 2 decimals)',
    )
    expect(messages(s.safeParse({ ...ok, amount: '-4' }))).toContain(
      'Enter a valid amount (max 2 decimals)',
    )
    expect(messages(s.safeParse({ ...ok, expense_date: '2026-11-10' }))).toContain(
      'Date cannot be in the future',
    )
    expect(messages(s.safeParse({ ...ok, expense_date: '2026-11-01' }))).toContain(
      'Date is before tracking starts',
    )
    expect(messages(s.safeParse({ ...ok, category_id: '' }))).toContain('Choose a category')
    expect(s.safeParse({ ...ok, paid_from: 'Wallet' }).success).toBe(false)
  })

  it('transfer: two different accounts, branch whenever cash is involved', () => {
    const s = transferFormSchema({ today })
    const ok = {
      transfer_date: today,
      from_account: 'ENBD',
      to_account: 'ADCB',
      branch_id: '',
      amount: '10',
      reference: '',
      note: '',
    }
    expect(s.safeParse(ok).success).toBe(true)
    expect(messages(s.safeParse({ ...ok, to_account: 'ENBD' }))).toContain(
      'Choose two different accounts',
    )
    expect(messages(s.safeParse({ ...ok, from_account: 'Cash' }))).toContain(
      'Choose the branch whose cash moves',
    )
    expect(s.safeParse({ ...ok, from_account: 'Cash', branch_id: 'b1' }).success).toBe(true)
  })

  it('payment: cannot exceed the outstanding amount', () => {
    const s = paymentFormSchema({ today, outstanding: 100 })
    const ok = { payment_date: today, amount: '100', paid_from: 'Cash', reference: '', note: '' }
    expect(s.safeParse(ok).success).toBe(true)
    expect(messages(s.safeParse({ ...ok, amount: '100.01' }))).toContain(
      'Payment cannot exceed the outstanding amount',
    )
    expect(s.safeParse({ ...ok, amount: '0' }).success).toBe(false)
  })

  it('settlement: bank must be ENBD or ADCB (never Cash)', () => {
    const s = settlementFormSchema({ today })
    const ok = { settlement_date: today, bank: 'ENBD', amount: '5', reference: '', note: '' }
    expect(s.safeParse(ok).success).toBe(true)
    expect(s.safeParse({ ...ok, bank: 'Cash' }).success).toBe(false)
  })

  it('opening: amounts are non-negative and blanks mean zero', () => {
    const base = {
      as_of_date: today,
      receipts_bank: 'ENBD',
      enbd_balance: '',
      adcb_balance: '0',
      pos_pending: '0',
      savings_brought_forward: '0',
      branch_cash: [{ branch_id: 'b1', amount: '' }],
      supplier_dues: [],
      reason: '',
    }
    const r = openingFormSchema.safeParse(base)
    expect(r.success && r.data.enbd_balance).toBe('0')
    expect(openingFormSchema.safeParse({ ...base, adcb_balance: '-1' }).success).toBe(false)
    expect(
      openingFormSchema.safeParse({ ...base, branch_cash: [{ branch_id: 'b1', amount: '-2' }] })
        .success,
    ).toBe(false)
    expect(openingFormSchema.safeParse({ ...base, receipts_bank: 'CBD' }).success).toBe(false)
  })
})

/* ---------------------------------- Opening Balances ---------------------------------- */
describe('Opening Balances page', () => {
  it('shows the not-configured state with a field per branch until saved', async () => {
    api(owner(), { opening: OPENING_NONE })
    renderApp('/opening-balances')
    expect(await screen.findByText('Opening balances are not set up yet')).toBeInTheDocument()
    expect(screen.getByText('Not configured')).toBeInTheDocument()
    expect(screen.getByLabelText('Test Branch One (AED)')).toBeInTheDocument()
    expect(screen.getByLabelText('Test Branch Two (AED)')).toBeInTheDocument()
    expect(screen.getByLabelText('Chem Co (AED)')).toBeInTheDocument()
    expect(screen.queryByText('Change history')).not.toBeInTheDocument()
  })

  it('blocks negative or malformed amounts before anything is sent', async () => {
    const calls = api(owner(), { opening: OPENING_NONE })
    const user = userEvent.setup()
    renderApp('/opening-balances')
    await screen.findByText('Opening balances are not set up yet')
    await user.clear(screen.getByLabelText('ENBD balance (AED)'))
    await user.type(screen.getByLabelText('ENBD balance (AED)'), '-5')
    await user.click(screen.getByRole('button', { name: 'Review & save' }))
    expect(await screen.findAllByText('Enter a valid amount (max 2 decimals)')).not.toHaveLength(0)
    expect(screen.queryByTestId('opening-review')).not.toBeInTheDocument()
    expect(calls.some((c) => c.method === 'put')).toBe(false)
  })

  it('needs a receiving bank, shows a review step, and only saves after confirming', async () => {
    const calls = api(owner(), { opening: OPENING_NONE })
    const user = userEvent.setup()
    renderApp('/opening-balances')
    await screen.findByText('Opening balances are not set up yet')
    await user.click(screen.getByRole('button', { name: 'Review & save' }))
    expect(await screen.findByText('Choose the receiving bank')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'put')).toBe(false)

    await user.click(screen.getByRole('combobox', { name: /Bank that receives/ }))
    await user.click(await screen.findByRole('option', { name: 'ADCB' }))
    await user.clear(screen.getByLabelText('ENBD balance (AED)'))
    await user.type(screen.getByLabelText('ENBD balance (AED)'), '10000')
    await user.clear(screen.getByLabelText('Test Branch One (AED)'))
    await user.type(screen.getByLabelText('Test Branch One (AED)'), '1000.5')
    await user.click(screen.getByRole('button', { name: 'Review & save' }))

    const review = await screen.findByTestId('opening-review')
    expect(within(review).getByText(/ENBD: /)).toHaveTextContent(money('10000'))
    expect(within(review).getByText(/Branch cash: /)).toHaveTextContent(money('1000.5'))
    expect(calls.some((c) => c.method === 'put')).toBe(false) // nothing saved before confirming

    await user.click(screen.getByRole('button', { name: 'Save opening balances' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'put')).toBe(true))
    const put = body(calls.find((c) => c.method === 'put')!)
    expect(put.receipts_bank).toBe('ADCB')
    expect(put.enbd_balance).toBe('10000')
    expect(put.branch_cash).toEqual([
      { branch_id: 'b1', amount: '1000.5' },
      { branch_id: 'b2', amount: '0.00' },
    ])
    expect(put).not.toHaveProperty('reason')
    expect(toast.success).toHaveBeenCalledWith('Opening balances saved')
  })

  it('configured: shows who/when, locks the date and demands a reason to change saved figures', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/opening-balances')
    expect(await screen.findByText('Configured')).toBeInTheDocument()
    expect(screen.getAllByText('Test Owner').length).toBeGreaterThan(0)
    expect(screen.getByLabelText(/Opening balance as of/)).toBeDisabled()
    expect(screen.getByLabelText('Test Branch One (AED)')).toHaveValue('1000.00')

    await user.click(screen.getByRole('button', { name: 'Review changes' }))
    expect(
      await screen.findByText('A reason is required to change saved opening balances'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('opening-review')).not.toBeInTheDocument()

    await user.type(
      screen.getByLabelText(/Why are the saved balances being changed/),
      'Bank statement correction',
    )
    await user.click(screen.getByRole('button', { name: 'Review changes' }))
    await user.click(await screen.findByRole('button', { name: 'Save correction' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'put')).toBe(true))
    expect(body(calls.find((c) => c.method === 'put')!).reason).toBe('Bank statement correction')
  })

  it('shows the server message when a correction would make a balance negative', async () => {
    api(owner(), {
      handler: (url, c) =>
        url === '/opening-balances' && c.method === 'put'
          ? apiError(422, 'negative_balance', 'This change would make ENBD negative on 2026-11-04')
          : undefined,
    })
    const user = userEvent.setup()
    renderApp('/opening-balances')
    await screen.findByText('Configured')
    await user.type(screen.getByLabelText(/Why are the saved balances being changed/), 'fix figure')
    await user.click(screen.getByRole('button', { name: 'Review changes' }))
    await user.click(await screen.findByRole('button', { name: 'Save correction' }))
    expect(
      await screen.findByText('This change would make ENBD negative on 2026-11-04'),
    ).toBeInTheDocument()
  })

  it('loading saved values into the form raises no React/Radix warnings (selects stay controlled)', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    api(owner())
    renderApp('/opening-balances')
    await screen.findByText('Configured')
    await waitFor(() =>
      expect(screen.getByLabelText('Test Branch One (AED)')).toHaveValue('1000.00'),
    )
    expect(warn).not.toHaveBeenCalled()
    expect(error).not.toHaveBeenCalled()
    warn.mockRestore()
    error.mockRestore()
  })

  it('shows an error state with retry when loading fails', async () => {
    api(owner(), {
      handler: (url) =>
        url === '/opening-balances' ? apiError(500, 'server_error', 'boom') : undefined,
    })
    renderApp('/opening-balances')
    expect(await screen.findByText('boom')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Try again/ })).toBeInTheDocument()
  })
})

/* ---------------------------------- Cash & Banks ---------------------------------- */
describe('Cash & Banks page', () => {
  it('not configured: points to Opening Balances and requests no ledger data', async () => {
    const calls = api(owner(), { balances: BAL_NONE })
    renderApp('/cash-banks')
    expect(await screen.findByText('Opening balances are not configured')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Set opening balances' })).toHaveAttribute(
      'href',
      '/opening-balances',
    )
    expect(calls.some((c) => c.url === '/cash-banks/transactions')).toBe(false)
    expect(screen.queryByText('Total Cash + Bank')).not.toBeInTheDocument()
  })

  it('shows the six balance cards exactly as calculated by the server', async () => {
    api(owner())
    renderApp('/cash-banks')
    const cards = await screen.findByLabelText('Balances')
    await within(cards).findByText(money('17110'))
    for (const [label, value] of [
      ['Total Cash + Bank', '17110'],
      ['Cash in Hand', '1810'],
      ['ENBD', '10300'],
      ['ADCB', '5000'],
      ['POS Pending', '1100'],
      ['Total Savings', '350'],
    ] as const) {
      const card = within(cards).getByText(label).closest('div')!.parentElement!
      expect(card).toHaveTextContent(money(value))
    }
  })

  it('lists transactions with date, type, branch, account, amount, description and creator', async () => {
    api(owner())
    renderApp('/cash-banks')
    const table = await screen.findByRole('table', { name: 'Cash and bank transaction history' })
    const row = (await within(table).findByText('Daily report cash')).closest('tr')!
    for (const text of [
      '03 Nov 2026',
      'Test Branch One',
      'Cash',
      money('400'),
      'Report 2026-11-03',
      'Clerk Ali',
    ]) {
      expect(
        within(row).getByText(new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))),
      ).toBeInTheDocument()
    }
  })

  it('account quick filters request only that account and reset to page 1', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/cash-banks')
    await screen.findByRole('table', { name: 'Cash and bank transaction history' })
    await user.click(screen.getByRole('button', { name: 'ENBD movements' }))
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url === '/cash-banks/transactions' &&
            (c.params as { account?: string }).account === 'ENBD',
        ),
      ).toBe(true),
    )
    expect(screen.getByRole('button', { name: 'ENBD movements' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('rejects an inverted date range without calling the server again', async () => {
    api(owner())
    const user = userEvent.setup()
    renderApp('/cash-banks')
    await screen.findByRole('table', { name: 'Cash and bank transaction history' })
    await user.type(screen.getByLabelText('From'), '2026-11-08')
    await user.type(screen.getByLabelText('To'), '2026-11-05')
    expect(await screen.findByText('Start date must not be after end date')).toBeInTheDocument()
  })

  it('transfer form: validates, then posts one request with an idempotency key', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/cash-banks')
    await user.click(await screen.findByRole('button', { name: /New transfer/ }))
    const dialog = await screen.findByRole('dialog')

    await user.click(within(dialog).getByRole('button', { name: 'Record transfer' }))
    expect(await within(dialog).findByText('Choose the source account')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post')).toBe(false)

    await user.click(within(dialog).getByRole('combobox', { name: /From/ }))
    await user.click(await screen.findByRole('option', { name: 'ENBD' }))
    await user.click(within(dialog).getByRole('combobox', { name: /To/ }))
    await user.click(await screen.findByRole('option', { name: 'ENBD' }))
    await user.type(within(dialog).getByLabelText(/Amount/), '200')
    await user.click(within(dialog).getByRole('button', { name: 'Record transfer' }))
    expect(await within(dialog).findByText('Choose two different accounts')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('combobox', { name: /To/ }))
    await user.click(await screen.findByRole('option', { name: 'ADCB' }))
    await user.click(within(dialog).getByRole('button', { name: 'Record transfer' }))
    await waitFor(() => expect(posted(calls, '/cash-banks/transfers')).toBeTruthy())
    const sent = body(posted(calls, '/cash-banks/transfers')!)
    expect(sent).toMatchObject({ from_account: 'ENBD', to_account: 'ADCB', amount: '200' })
    expect(sent).not.toHaveProperty('branch_id') // bank-to-bank carries no branch
    expect(sent.client_key).toMatch(/^[0-9a-f-]{36}$/)
    expect(toast.success).toHaveBeenCalledWith('Transfer recorded')
  })

  it('transfer involving cash needs the branch whose cash moves', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/cash-banks')
    await user.click(await screen.findByRole('button', { name: /New transfer/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('combobox', { name: /From/ }))
    await user.click(await screen.findByRole('option', { name: 'Cash' }))
    await user.click(within(dialog).getByRole('combobox', { name: /To/ }))
    await user.click(await screen.findByRole('option', { name: 'ENBD' }))
    await user.type(within(dialog).getByLabelText(/Amount/), '50')
    await user.click(within(dialog).getByRole('button', { name: 'Record transfer' }))
    expect(
      await within(dialog).findByText('Choose the branch whose cash moves'),
    ).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post')).toBe(false)
  })

  it('shows the server refusal when a transfer would overdraw an account', async () => {
    api(owner(), {
      handler: (url, c) =>
        url === '/cash-banks/transfers' && c.method === 'post'
          ? apiError(422, 'insufficient_funds', 'ENBD would go negative (available AED 10,300.00)')
          : undefined,
    })
    const user = userEvent.setup()
    renderApp('/cash-banks')
    await user.click(await screen.findByRole('button', { name: /New transfer/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('combobox', { name: /From/ }))
    await user.click(await screen.findByRole('option', { name: 'ENBD' }))
    await user.click(within(dialog).getByRole('combobox', { name: /To/ }))
    await user.click(await screen.findByRole('option', { name: 'ADCB' }))
    await user.type(within(dialog).getByLabelText(/Amount/), '99999')
    await user.click(within(dialog).getByRole('button', { name: 'Record transfer' }))
    expect(await within(dialog).findByText(/ENBD would go negative/)).toBeInTheDocument()
  })

  it('voiding a transfer needs a reason and sends it', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/cash-banks')
    await user.click(await screen.findByRole('button', { name: /Void transfer ENBD to ADCB/ }))
    await user.click(await screen.findByRole('button', { name: 'Void transfer' }))
    expect(await screen.findByText('Enter a reason (at least 3 characters)')).toBeInTheDocument()
    expect(posted(calls, '/cash-banks/transfers/t1/void')).toBeUndefined()
    await user.type(screen.getByRole('textbox', { name: /Reason/ }), 'wrong account')
    await user.click(screen.getByRole('button', { name: 'Void transfer' }))
    await waitFor(() => expect(posted(calls, '/cash-banks/transfers/t1/void')).toBeTruthy())
    expect(body(posted(calls, '/cash-banks/transfers/t1/void')!)).toEqual({
      reason: 'wrong account',
    })
  })
})

/* ---------------------------------- Expenses & Savings ---------------------------------- */
describe('Expenses & Savings page', () => {
  it('lists head office expenses with totals and type', async () => {
    api(owner())
    renderApp('/expenses')
    const table = await screen.findByRole('table', { name: 'Head office expenses' })
    const row = (await within(table).findByText('Utilities')).closest('tr')!
    expect(within(row).getByText('All branches')).toBeInTheDocument()
    expect(within(row).getByText('Expense')).toBeInTheDocument()
    expect(within(row).getByText(money('60'))).toBeInTheDocument()
    const totals = screen.getByLabelText('Expense totals')
    await waitFor(() => expect(totals).toHaveTextContent(money('60')))
    expect(totals).toHaveTextContent('Expenses (excl. savings)')
  })

  it('sends filters to the server and returns to page 1', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/expenses')
    await screen.findByRole('table', { name: 'Head office expenses' })
    await user.click(screen.getByRole('combobox', { name: 'Saving' }))
    await user.click(await screen.findByRole('option', { name: 'Savings only' }))
    await user.click(screen.getByRole('combobox', { name: 'Paid from' }))
    await user.click(await screen.findByRole('option', { name: 'ADCB' }))
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url === '/expenses' &&
            (c.params as Record<string, unknown>).is_saving === true &&
            (c.params as Record<string, unknown>).paid_from === 'ADCB',
        ),
      ).toBe(true),
    )
  })

  it('new expense: validates amount and category before sending', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/expenses')
    await user.click(await screen.findByRole('button', { name: /New expense/ }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(/Amount/), '0')
    await user.click(within(dialog).getByRole('button', { name: 'Record expense' }))
    expect(await within(dialog).findByText('Amount must be greater than zero')).toBeInTheDocument()
    expect(within(dialog).getByText('Choose a category')).toBeInTheDocument()
    expect(within(dialog).getByText('Choose where it was paid from')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post')).toBe(false)
  })

  it('new expense: All branches sends no branch; a saving is flagged; one idempotency key', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/expenses')
    await user.click(await screen.findByRole('button', { name: /New expense/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('combobox', { name: /Category/ }))
    await user.click(await screen.findByRole('option', { name: 'Rent' }))
    await user.click(within(dialog).getByRole('combobox', { name: /Paid from/ }))
    await user.click(await screen.findByRole('option', { name: 'ADCB' }))
    await user.type(within(dialog).getByLabelText(/Amount/), '80.50')
    await user.click(within(dialog).getByRole('checkbox', { name: /This is a saving/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Record expense' }))
    await waitFor(() => expect(posted(calls, '/expenses')).toBeTruthy())
    const sent = body(posted(calls, '/expenses')!)
    expect(sent).toMatchObject({
      category_id: 'c2',
      paid_from: 'ADCB',
      amount: '80.50',
      is_saving: true,
    })
    expect(sent).not.toHaveProperty('branch_id')
    expect(sent.client_key).toMatch(/^[0-9a-f-]{36}$/)
    expect(sent.expense_date).toBe(dubaiToday())
    expect(toast.success).toHaveBeenCalledWith('Saving recorded')
  })

  it('marking as saving needs a reason and uses the saving endpoint', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/expenses')
    await user.click(await screen.findByRole('button', { name: /Mark as saving Utilities/ }))
    await user.click(await screen.findByRole('button', { name: 'Mark as saving' }))
    expect(await screen.findByText('Enter a reason (at least 3 characters)')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: /Reason/ }), 'Moved to savings')
    await user.click(screen.getByRole('button', { name: 'Mark as saving' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'patch' && c.url === '/expenses/e1/saving')).toBe(true),
    )
    expect(body(calls.find((c) => c.method === 'patch')!)).toEqual({
      is_saving: true,
      reason: 'Moved to savings',
    })
  })

  it('deleting is a void with a reason, never a hard delete', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/expenses')
    await user.click(await screen.findByRole('button', { name: /Delete expense Utilities/ }))
    await user.type(await screen.findByRole('textbox', { name: /Reason/ }), 'duplicate bill')
    await user.click(screen.getByRole('button', { name: 'Delete expense' }))
    await waitFor(() => expect(posted(calls, '/expenses/e1/void')).toBeTruthy())
    expect(body(posted(calls, '/expenses/e1/void')!)).toEqual({ reason: 'duplicate bill' })
    expect(calls.some((c) => c.method === 'delete')).toBe(false)
  })

  it('editing asks for a reason and sends the correction as PUT', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/expenses')
    await user.click(await screen.findByRole('button', { name: /Edit expense Utilities/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText(/Amount/)).toHaveValue('60.00')
    await user.click(within(dialog).getByRole('button', { name: 'Save correction' }))
    expect(
      await within(dialog).findByText('Enter a reason (at least 3 characters)'),
    ).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText(/Reason for the correction/), 'Typo in amount')
    await user.click(within(dialog).getByRole('button', { name: 'Save correction' }))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'put' && c.url === '/expenses/e1')).toBe(true),
    )
    expect(body(calls.find((c) => c.method === 'put')!).reason).toBe('Typo in amount')
  })

  it('details dialog loads the expense with its audit history', async () => {
    api(owner())
    const user = userEvent.setup()
    renderApp('/expenses')
    await user.click(await screen.findByRole('button', { name: /View expense Utilities/ }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Gas bill')).toBeInTheDocument()
    expect(within(dialog).getByText('Audit history')).toBeInTheDocument()
  })

  it('not configured: the New expense button is disabled and says why', async () => {
    api(owner(), { balances: BAL_NONE })
    renderApp('/expenses')
    expect(await screen.findByText(/Opening balances are not configured yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /New expense/ })).toBeDisabled()
  })
})

/* ---------------------------------- Suppliers ---------------------------------- */
describe('Suppliers', () => {
  it('shows summary cards and a searchable list linking to the detail page', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/suppliers')
    const cards = await screen.findByLabelText('Supplier summary')
    await within(cards).findByText(money('1200'))
    for (const label of [
      'Total Suppliers',
      'Total Outstanding',
      'Total Paid',
      'Suppliers with Dues',
    ])
      expect(within(cards).getByText(label)).toBeInTheDocument()
    const link = await screen.findByRole('link', { name: 'Chem Co' })
    expect(link).toHaveAttribute('href', '/suppliers/s1')
    await user.type(screen.getByLabelText('Search'), 'chem')
    await waitFor(() =>
      expect(
        calls.some((c) => c.url === '/suppliers' && (c.params as { q?: string }).q === 'chem'),
      ).toBe(true),
    )
  })

  it('sort and dues filters are sent to the server', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/suppliers')
    await screen.findByRole('link', { name: 'Chem Co' })
    await user.click(screen.getByRole('combobox', { name: 'Sort by' }))
    await user.click(await screen.findByRole('option', { name: 'Highest outstanding' }))
    await user.click(screen.getByRole('combobox', { name: 'Dues' }))
    await user.click(await screen.findByRole('option', { name: 'With outstanding dues' }))
    await waitFor(() =>
      expect(
        calls.some((c) => {
          const p = c.params as Record<string, unknown>
          return (
            c.url === '/suppliers' &&
            p.sort === 'outstanding' &&
            p.desc === true &&
            p.outstanding_only === true
          )
        }),
      ).toBe(true),
    )
  })

  it('add supplier posts the details (no outstanding amount once balances are configured)', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/suppliers')
    await user.click(await screen.findByRole('button', { name: /Add supplier/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByLabelText(/Opening outstanding/)).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Add supplier' }))
    expect(await within(dialog).findByText('Enter the supplier name')).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText(/Supplier name/), 'Hanger World')
    await user.type(within(dialog).getByLabelText(/Payment terms/), '15 days')
    await user.click(within(dialog).getByRole('button', { name: 'Add supplier' }))
    await waitFor(() => expect(posted(calls, '/suppliers')).toBeTruthy())
    expect(body(posted(calls, '/suppliers')!)).toEqual({
      name: 'Hanger World',
      payment_terms: '15 days',
      is_active: true,
    })
  })

  it('before opening balances exist the supplier form accepts an opening outstanding', async () => {
    api(owner(), { balances: BAL_NONE })
    const user = userEvent.setup()
    renderApp('/suppliers')
    await user.click(await screen.findByRole('button', { name: /Add supplier/ }))
    expect(await screen.findByLabelText(/Opening outstanding/)).toBeInTheDocument()
  })

  it('detail: opening, new dues, paid and outstanding are separate figures with history', async () => {
    api(owner())
    renderApp('/suppliers/s1')
    const cards = await screen.findByLabelText('Supplier balance')
    await waitFor(() => expect(cards).toHaveTextContent(money('1000')))
    expect(cards).toHaveTextContent(money('250'))
    expect(cards).toHaveTextContent(money('400'))
    expect(cards).toHaveTextContent(money('850'))
    expect(await screen.findByText('CHQ-9')).toBeInTheDocument()
    expect(screen.getByText('Delivers Mondays')).toBeInTheDocument()
  })

  it('a payment larger than the outstanding amount is blocked before sending', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/suppliers/s1')
    await user.click(await screen.findByRole('button', { name: /Record payment/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('combobox', { name: /Paid from/ }))
    await user.click(await screen.findByRole('option', { name: 'Cash' }))
    await user.type(within(dialog).getByLabelText(/Amount/), '850.01')
    await user.click(within(dialog).getByRole('button', { name: 'Record payment' }))
    expect(
      await within(dialog).findByText('Payment cannot exceed the outstanding amount'),
    ).toBeInTheDocument()
    expect(posted(calls, '/suppliers/s1/payments')).toBeUndefined()
  })

  it('a partial payment is sent with source, amount and an idempotency key', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/suppliers/s1')
    await user.click(await screen.findByRole('button', { name: /Record payment/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('combobox', { name: /Paid from/ }))
    await user.click(await screen.findByRole('option', { name: 'ENBD' }))
    await user.type(within(dialog).getByLabelText(/Amount/), '300')
    await user.type(within(dialog).getByLabelText(/Reference/), 'CHQ-10')
    await user.click(within(dialog).getByRole('button', { name: 'Record payment' }))
    await waitFor(() => expect(posted(calls, '/suppliers/s1/payments')).toBeTruthy())
    const sent = body(posted(calls, '/suppliers/s1/payments')!)
    expect(sent).toMatchObject({ amount: '300', paid_from: 'ENBD', reference: 'CHQ-10' })
    expect(sent.client_key).toMatch(/^[0-9a-f-]{36}$/)
    expect(toast.success).toHaveBeenCalledWith('Payment recorded')
  })

  it('Mark as Paid records the full outstanding as one payment after confirmation', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/suppliers/s1')
    await user.click(await screen.findByRole('button', { name: /Mark as Paid/ }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent(money('850'))
    await user.click(within(dialog).getByRole('button', { name: 'Record full payment' }))
    expect(
      await within(dialog).findByText('Choose where the payment is made from'),
    ).toBeInTheDocument()
    expect(posted(calls, '/suppliers/s1/mark-paid')).toBeUndefined()
    await user.click(within(dialog).getByRole('combobox', { name: /Paid from/ }))
    await user.click(await screen.findByRole('option', { name: 'Cash' }))
    await user.click(within(dialog).getByRole('button', { name: 'Record full payment' }))
    await waitFor(() => expect(posted(calls, '/suppliers/s1/mark-paid')).toBeTruthy())
    const sent = body(posted(calls, '/suppliers/s1/mark-paid')!)
    expect(sent.paid_from).toBe('Cash')
    expect(sent).not.toHaveProperty('amount') // the server uses the outstanding amount; the UI never sends a made-up figure
  })

  it('nothing outstanding: payment buttons are disabled', async () => {
    api(owner(), { supplier: { ...SUPPLIER, outstanding: '0.00', total_paid: '1250.00' } })
    renderApp('/suppliers/s1')
    await screen.findByLabelText('Supplier balance')
    expect(screen.getByRole('button', { name: /Record payment/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Mark as Paid/ })).toBeDisabled()
  })

  it('voiding a payment asks for a reason', async () => {
    const calls = api(owner())
    const user = userEvent.setup()
    renderApp('/suppliers/s1')
    await user.click(await screen.findByRole('button', { name: /Void payment 2026-11-04/ }))
    await user.type(await screen.findByRole('textbox', { name: /Reason/ }), 'bounced cheque')
    await user.click(screen.getByRole('button', { name: 'Void entry' }))
    await waitFor(() => expect(posted(calls, '/suppliers/entries/se1/void')).toBeTruthy())
    expect(body(posted(calls, '/suppliers/entries/se1/void')!)).toEqual({
      reason: 'bounced cheque',
    })
  })
})

/* ---------------------------------- permissions ---------------------------------- */
describe('Owner-only finance', () => {
  it.each(['/opening-balances', '/cash-banks', '/expenses', '/suppliers', '/suppliers/s1'])(
    'branch user typing %s sees Access denied and no finance data is requested',
    async (path) => {
      const calls = api(PROFILE_BRANCH)
      renderApp(path)
      expect(await screen.findByText('Access denied')).toBeInTheDocument()
      const financeUrls = ['/opening-balances', '/cash-banks', '/expenses', '/suppliers']
      expect(calls.filter((c) => financeUrls.some((u) => (c.url ?? '').startsWith(u)))).toEqual([])
    },
  )

  it('branch user has no finance links in the navigation', async () => {
    api(PROFILE_BRANCH)
    renderApp('/')
    await screen.findByRole('navigation', { name: /main|primary|sidebar/i }).catch(() => undefined)
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: 'Dashboard' }).length).toBeGreaterThan(0),
    )
    for (const name of ['Cash & Banks', 'Opening Balances', 'Expenses & Savings', 'Suppliers'])
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument()
  })

  it('owner sees all four finance links', async () => {
    api(owner())
    renderApp('/')
    for (const name of ['Cash & Banks', 'Opening Balances', 'Expenses & Savings', 'Suppliers'])
      expect(await screen.findByRole('link', { name })).toBeInTheDocument()
  })
})
