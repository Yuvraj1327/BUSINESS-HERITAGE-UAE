import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { customerFormSchema, orderFormSchema, previewFinalPayable } from '@/schemas/orders'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  PROFILE_BRANCH,
  PROFILE_OWNER,
  apiError,
  renderApp,
  stubApi,
  type ApiReply,
} from '@/test/render-app'
import { dubaiParts, formatDateTime } from '@/utils/format'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const row = (over: Record<string, unknown> = {}) => ({
  id: 'o1',
  order_no: 'ORD-0001',
  customer_id: 'c1',
  customer_name: 'Aisha Khan',
  mobile: '0501234567',
  area: 'Satwa',
  branch_id: 'b1',
  branch_name: 'SATWA',
  category: 'Wash & Fold',
  service_type: 'Standard',
  status: 'Scheduled',
  payment_status: 'Partial',
  order_date: '2026-11-10',
  pickup_at: '2026-11-10T06:00:00Z',
  pickup_address: 'Villa 4',
  delivery_at: '2026-11-12T10:00:00Z',
  delivery_address: 'Villa 4',
  final_payable: '100.00',
  amount_collected: '40.00',
  outstanding: '60.00',
  overdue: null,
  ...over,
})
const detail = (over: Record<string, unknown> = {}) => ({
  order: row(),
  category_id: 'cat1',
  notes: 'Handle with care',
  order_total: '100.00',
  discount: '0.00',
  service_fee: '0.00',
  cancel_reason: null,
  cancelled_at: null,
  delivered_at: null,
  customer_whatsapp: null,
  customer_address: 'Villa 4, Satwa',
  created_at: '2026-11-10T05:00:00Z',
  created_by_name: 'Test Owner',
  updated_at: '2026-11-10T05:00:00Z',
  updated_by_name: null,
  payments: [
    {
      id: 'p1',
      payment_date: '2026-11-10',
      amount: '40.00',
      method: 'Cash',
      reference: null,
      note: null,
      recorded_by: 'Test Owner',
      created_at: '2026-11-10T05:00:00Z',
    },
  ],
  history: [
    {
      id: 1,
      from_status: null,
      to_status: 'New',
      changed_by: 'Test Owner',
      changed_at: '2026-11-10T05:00:00Z',
      note: null,
    },
    {
      id: 2,
      from_status: 'New',
      to_status: 'Scheduled',
      changed_by: 'Test Owner',
      changed_at: '2026-11-10T05:30:00Z',
      note: null,
    },
  ],
  next_status: 'Picked Up',
  can_edit: true,
  can_cancel: true,
  can_pay: true,
  ...over,
})
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const customer = {
  id: 'c1',
  branch_id: 'b1',
  branch_name: 'SATWA',
  name: 'Aisha Khan',
  mobile: '0501234567',
  whatsapp: null,
  address: 'Villa 4',
  area: 'Satwa',
  notes: null,
  order_count: 3,
  total_billed: '300.00',
  outstanding: '60.00',
  last_order_date: '2026-11-10',
  created_at: '2026-11-01T05:00:00Z',
}
const DASH = {
  date: '2026-11-10',
  kpis: {
    total_orders: 12,
    todays_pickups: 3,
    todays_deliveries: 2,
    monthly_revenue: '2500.00',
    outstanding_payments: '410.00',
  },
  sections: [
    { key: 'pickups_today', title: "Today's Pickup Schedule", count: 1, items: [row()] },
    { key: 'pending_pickups', title: 'Pending Pickups', count: 0, items: [] },
  ],
}
const REPORT = {
  key: 'order_summary',
  title: 'Order totals',
  description: 'Order totals for the period.',
  filters: {
    date_from: '2026-11-01',
    date_to: '2026-11-10',
    period: 'day',
    branch_id: null,
    branch_name: 'All Branches',
  },
  columns: [
    { key: 'metric', label: 'Measure', kind: 'text' },
    { key: 'value', label: 'Value', kind: 'money' },
  ],
  rows: [{ metric: 'Revenue', value: '2500.00' }],
  total: 1,
  page: 1,
  page_size: 25,
  summary: [],
  notes: ['Order revenue is separate from Daily Reports sales.'],
  generated_at: '2026-11-10T08:00:00Z',
}

interface Opts {
  detail?: unknown
  createReply?: ApiReply
  paymentReply?: ApiReply
  statusReply?: ApiReply
  customerReply?: ApiReply
}
function api(profile: object, o: Opts = {}) {
  return stubApi((c): ApiReply => {
    const url = c.url ?? ''
    const method = (c.method ?? 'get').toLowerCase()
    if (url === '/branches')
      return { status: 200, body: [{ id: 'b1', name: 'SATWA', sort_order: 1, is_active: true }] }
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
    if (url === '/orders/dashboard') return { status: 200, body: DASH }
    if (url === '/orders/service-categories')
      return { status: 200, body: [{ id: 'cat1', name: 'Wash & Fold', is_active: true }] }
    if (url === '/orders/reports/catalog')
      return {
        status: 200,
        body: [
          { key: 'order_summary', title: 'Order totals', category: 'Orders', description: 'x' },
        ],
      }
    if (url.endsWith('/export')) return { status: 200, body: new Blob(['a,b']) }
    if (url === '/orders/reports/order_summary') return { status: 200, body: REPORT }
    if (url === '/order-operations/counts')
      return { status: 200, body: { pickups_today: 1, processing: 4, ready: 2 } }
    if (url.startsWith('/order-operations/')) return { status: 200, body: page([row()]) }
    if (url === '/customers' && method === 'post')
      return o.customerReply ?? { status: 200, body: customer }
    if (url === '/customers') return { status: 200, body: page([customer]) }
    if (url === '/customers/c1') return { status: 200, body: customer }
    if (url === '/customers/c1/orders') return { status: 200, body: page([row()]) }
    if (url === '/orders' && method === 'post')
      return o.createReply ?? { status: 200, body: detail() }
    if (url === '/orders') return { status: 200, body: page([row()]) }
    if (url === '/orders/o1/status')
      return o.statusReply ?? { status: 200, body: detail({ next_status: 'Processing' }) }
    if (url === '/orders/o1/cancel') return { status: 200, body: detail() }
    if (url === '/orders/o1/payments')
      return (
        o.paymentReply ?? {
          status: 201,
          body: {
            order_id: 'o1',
            final_payable: '100.00',
            amount_collected: '100.00',
            outstanding: '0.00',
            payment_status: 'Paid',
          },
        }
      )
    if (url === '/orders/o1') return { status: 200, body: o.detail ?? detail() }
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

describe('order rules in the browser (display and input checks only; the server is the authority)', () => {
  it('previews final payable as total - discount + service fee in whole fils', () => {
    expect(previewFinalPayable('100', '10', '5')).toBe(95)
    expect(previewFinalPayable('10.10', '0.05', '0.20')).toBe(10.25)
    expect(previewFinalPayable('abc', '0', '0')).toBeNull()
    expect(previewFinalPayable('-5', '0', '0')).toBeNull()
  })

  const base = {
    category_id: 'cat1',
    service_type: 'Standard' as const,
    notes: '',
    pickup_date: '2026-11-10',
    pickup_time: '10:00',
    pickup_address: '',
    delivery_date: '2026-11-12',
    delivery_time: '12:00',
    delivery_address: '',
    order_total: '100',
    discount: '0',
    service_fee: '0',
  }
  it('accepts a valid order and rejects delivery before pickup, half a schedule, and negatives', () => {
    expect(orderFormSchema.safeParse(base).success).toBe(true)
    expect(orderFormSchema.safeParse({ ...base, delivery_date: '2026-11-09' }).success).toBe(false)
    expect(orderFormSchema.safeParse({ ...base, pickup_time: '' }).success).toBe(false)
    expect(orderFormSchema.safeParse({ ...base, order_total: '-1' }).success).toBe(false)
    expect(orderFormSchema.safeParse({ ...base, discount: '1.234' }).success).toBe(false)
    expect(orderFormSchema.safeParse({ ...base, pickup_date: '', pickup_time: '' }).success).toBe(
      true,
    )
  })
  it('validates the customer mobile number', () => {
    const ok = {
      name: 'Aisha',
      mobile: '+971 50 123 4567',
      whatsapp: '',
      address: '',
      area: '',
      notes: '',
    }
    expect(customerFormSchema.safeParse(ok).success).toBe(true)
    expect(customerFormSchema.safeParse({ ...ok, mobile: 'call me' }).success).toBe(false)
    expect(customerFormSchema.safeParse({ ...ok, mobile: '12' }).success).toBe(false)
    expect(customerFormSchema.safeParse({ ...ok, name: ' ' }).success).toBe(false)
  })
  it('shows times in Dubai regardless of the browser zone', () => {
    expect(dubaiParts('2026-11-10T21:30:00Z')).toEqual({ date: '2026-11-11', time: '01:30' })
    expect(formatDateTime('2026-11-10T06:00:00Z')).toMatch(/10 Nov 2026/)
    expect(formatDateTime(null)).toBe('—')
  })
})

describe('Order Management dashboard', () => {
  it('shows the five KPI cards and the schedule sections', async () => {
    const calls = api(PROFILE_OWNER)
    renderApp('/order-management')
    expect(
      await screen.findByRole('heading', { name: 'Order Management', level: 1 }),
    ).toBeInTheDocument()
    const k = await screen.findByLabelText('Key figures')
    await waitFor(() => expect(within(k).getByText('12')).toBeInTheDocument())
    for (const l of [
      'Total Orders',
      "Today's Pickups",
      "Today's Deliveries",
      'Monthly Revenue',
      'Outstanding Payments',
    ])
      expect(within(k).getByText(l)).toBeInTheDocument()
    expect(within(k).getByText(/2,500\.00/)).toBeInTheDocument()
    expect(within(k).getByText(/410\.00/)).toBeInTheDocument()
    expect(
      await screen.findByRole('heading', { name: "Today's Pickup Schedule" }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'ORD-0001' }).length).toBeGreaterThan(0)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
    expect(calls.find((c) => c.url === '/orders/dashboard')!.params).not.toHaveProperty('branch_id')
  })

  it('shows an error with a retry when the dashboard cannot load', async () => {
    stubApi((c): ApiReply => {
      if (c.url === '/orders/dashboard') return apiError(500, 'internal_error')
      if (c.url === '/branches') return { status: 200, body: [] }
      if (c.url === '/alerts/summary')
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
      return { status: 200, body: PROFILE_OWNER }
    })
    renderApp('/order-management')
    expect(await screen.findByText(/dashboard could not be loaded/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('Orders list', () => {
  it('searches by order number, name or mobile and sends the filters to the server', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/orders')
    expect(await screen.findByRole('link', { name: 'ORD-0001' })).toBeInTheDocument()
    await user.type(screen.getByRole('searchbox', { name: 'Search orders' }), '0501')
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/orders').at(-1)!.params).toMatchObject({ q: '0501' }),
    )
    expect(calls.find((c) => c.url === '/orders')!.params).not.toHaveProperty('status')
    await user.type(screen.getByLabelText('Pickup date'), '2026-11-10')
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/orders').at(-1)!.params).toMatchObject({
        pickup_date: '2026-11-10',
      }),
    )
  })

  it('warns when the date range is reversed instead of querying', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER)
    renderApp('/orders')
    await screen.findByRole('link', { name: 'ORD-0001' })
    await user.type(screen.getByLabelText('Order date from'), '2026-11-10')
    await user.type(screen.getByLabelText('Order date to'), '2026-11-01')
    expect(await screen.findByText(/start date must be on or before/i)).toBeInTheDocument()
  })

  it('offers New Order to a branch user and hides the branch filter', async () => {
    api(PROFILE_BRANCH)
    renderApp('/orders')
    expect(await screen.findByRole('link', { name: /New Order/ })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Branch' })).not.toBeInTheDocument()
  })

  it('denies a user who holds no order permission', async () => {
    const noOrders = {
      ...PROFILE_BRANCH,
      permissions: { dashboard: PROFILE_BRANCH.permissions.dashboard },
    }
    api(noOrders)
    renderApp('/orders')
    expect(await screen.findByText('Access denied')).toBeInTheDocument()
  })
})

describe('New order', () => {
  async function fillNewCustomerOrder(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: 'New customer' }))
    await user.type(screen.getByLabelText(/Customer name/), 'Aisha Khan')
    await user.type(screen.getByLabelText(/Mobile number/), '0501234567')
    await user.click(screen.getByRole('combobox', { name: /Service category/ }))
    await user.click(await screen.findByRole('option', { name: 'Wash & Fold' }))
    await user.type(screen.getByLabelText(/Delivery date/), '2026-11-12')
    await user.type(screen.getByLabelText(/Delivery time/), '12:00')
    await user.type(screen.getByLabelText(/Order total/), '100')
  }

  it('creates an order with a new customer, one idempotency key, and opens the order', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_BRANCH)
    renderApp('/orders/new')
    await screen.findByRole('heading', { name: 'New Order', level: 1 })
    await fillNewCustomerOrder(user)
    expect(screen.getByText(/Final payable:/)).toHaveTextContent('100.00')
    await user.click(screen.getByRole('button', { name: 'Create order' }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Order ORD-0001 created'))
    const post = calls.find((c) => c.url === '/orders' && c.method === 'post')!
    const body = JSON.parse(String(post.data))
    expect(body.new_customer).toMatchObject({ name: 'Aisha Khan', mobile: '0501234567' })
    expect(body.customer_id).toBeUndefined()
    expect(body.order_total).toBe('100')
    expect(body.client_key).toMatch(/^[0-9a-f-]{36}$/)
    expect(body).not.toHaveProperty('branch_id') // a branch user never chooses a branch
    expect(body).not.toHaveProperty('initial_payment')
    expect(await screen.findByRole('heading', { name: /Order ORD-0001/ })).toBeInTheDocument()
  })

  it('includes the payment taken now when asked', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_BRANCH)
    renderApp('/orders/new')
    await screen.findByRole('heading', { name: 'New Order', level: 1 })
    await fillNewCustomerOrder(user)
    await user.click(screen.getByRole('checkbox', { name: 'Record a payment now' }))
    await user.type(screen.getByLabelText(/Amount collected/), '40')
    await user.click(screen.getByRole('button', { name: 'Create order' }))
    await waitFor(() => expect(toast.success).toHaveBeenCalled())
    const body = JSON.parse(
      String(calls.find((c) => c.url === '/orders' && c.method === 'post')!.data),
    )
    expect(body.initial_payment).toMatchObject({ amount: '40', method: 'Cash' })
  })

  it('shows field errors and sends nothing when the form is incomplete', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_BRANCH)
    renderApp('/orders/new')
    await screen.findByRole('heading', { name: 'New Order', level: 1 })
    await user.click(screen.getByRole('button', { name: 'Create order' }))
    expect(await screen.findByText('Choose a service category')).toBeInTheDocument()
    expect(screen.getByText('Choose the expected delivery date')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/orders' && c.method === 'post')).toBe(false)
  })

  it('blocks delivery earlier than pickup', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_BRANCH)
    renderApp('/orders/new')
    await screen.findByRole('heading', { name: 'New Order', level: 1 })
    await fillNewCustomerOrder(user)
    await user.type(screen.getByLabelText('Pickup date'), '2026-11-13')
    await user.type(screen.getByLabelText('Pickup time'), '09:00')
    await user.click(screen.getByRole('button', { name: 'Create order' }))
    expect(
      await screen.findByText('Expected delivery cannot be earlier than the pickup'),
    ).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/orders' && c.method === 'post')).toBe(false)
  })

  it('shows the server message for a duplicate customer mobile', async () => {
    const user = userEvent.setup()
    api(PROFILE_BRANCH, {
      createReply: {
        status: 409,
        body: {
          error: {
            code: 'duplicate_customer',
            message:
              'This mobile number already belongs to Aisha Khan. Select that customer instead.',
          },
        },
      },
    })
    renderApp('/orders/new')
    await screen.findByRole('heading', { name: 'New Order', level: 1 })
    await fillNewCustomerOrder(user)
    await user.click(screen.getByRole('button', { name: 'Create order' }))
    expect(await screen.findByRole('alert', { name: '' })).toBeDefined()
    expect(await screen.findByText(/already belongs to Aisha Khan/)).toBeInTheDocument()
  })

  it('finds and selects an existing customer', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_BRANCH)
    renderApp('/orders/new')
    await screen.findByRole('heading', { name: 'New Order', level: 1 })
    await user.type(screen.getByRole('searchbox', { name: 'Find a customer' }), 'Aisha')
    await user.click(await screen.findByRole('button', { name: /Aisha Khan/ }))
    expect(screen.getByText(/Selected:/)).toHaveTextContent('Aisha Khan')
    await user.click(screen.getByRole('combobox', { name: /Service category/ }))
    await user.click(await screen.findByRole('option', { name: 'Wash & Fold' }))
    await user.type(screen.getByLabelText(/Delivery date/), '2026-11-12')
    await user.type(screen.getByLabelText(/Delivery time/), '12:00')
    await user.type(screen.getByLabelText(/Order total/), '100')
    await user.click(screen.getByRole('button', { name: 'Create order' }))
    await waitFor(() => expect(toast.success).toHaveBeenCalled())
    const body = JSON.parse(
      String(calls.find((c) => c.url === '/orders' && c.method === 'post')!.data),
    )
    expect(body.customer_id).toBe('c1')
    expect(body.new_customer).toBeUndefined()
  })
})

describe('Order details', () => {
  it('shows the customer, schedule, payment summary, timeline and payment history', async () => {
    api(PROFILE_OWNER)
    renderApp('/orders/o1')
    expect(await screen.findByRole('heading', { name: /Order ORD-0001/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Aisha Khan' })).toHaveAttribute(
      'href',
      '/customers/c1',
    )
    const tl = screen.getByRole('list', { name: 'Status timeline' })
    expect(within(tl).getByText('New → Scheduled')).toBeInTheDocument()
    expect(screen.getByText('Outstanding').nextSibling).toHaveTextContent('60.00')
    const pays = screen.getByRole('table', { name: 'Payment history' })
    expect(within(pays).getByText('Cash')).toBeInTheDocument()
    expect(screen.getByText(/Refunds need an approved workflow/)).toBeInTheDocument()
  })

  it('moves to the next status only after confirmation', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/orders/o1')
    await user.click(await screen.findByRole('button', { name: 'Mark Picked Up' }))
    expect(calls.some((c) => c.url === '/orders/o1/status')).toBe(false)
    await user.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Mark Picked Up' }),
    )
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Order marked Picked Up'))
    expect(
      JSON.parse(String(calls.find((c) => c.url === '/orders/o1/status')!.data)),
    ).toMatchObject({
      status: 'Picked Up',
    })
  })

  it('shows the server message when a status change is refused', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER, {
      statusReply: {
        status: 422,
        body: { error: { code: 'invalid_transition', message: 'An order cannot skip a step.' } },
      },
    })
    renderApp('/orders/o1')
    await user.click(await screen.findByRole('button', { name: 'Mark Picked Up' }))
    await user.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Mark Picked Up' }),
    )
    expect(await screen.findByText('An order cannot skip a step.')).toBeInTheDocument()
  })

  it('cancels only with a reason and keeps the order', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/orders/o1')
    await user.click(await screen.findByRole('button', { name: 'Cancel order' }))
    const dlg = screen.getByRole('alertdialog')
    await user.click(within(dlg).getByRole('button', { name: 'Cancel order' }))
    expect(calls.some((c) => c.url === '/orders/o1/cancel')).toBe(false)
    await user.type(within(dlg).getByRole('textbox'), 'Customer changed plans')
    await user.click(within(dlg).getByRole('button', { name: 'Cancel order' }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Order cancelled'))
    expect(
      JSON.parse(String(calls.find((c) => c.url === '/orders/o1/cancel')!.data)),
    ).toMatchObject({
      reason: 'Customer changed plans',
      confirm: true,
    })
  })

  it('hides cancel from a branch user and hides every action on a finished order', async () => {
    api(PROFILE_BRANCH)
    renderApp('/orders/o1')
    await screen.findByRole('heading', { name: /Order ORD-0001/ })
    expect(screen.queryByRole('button', { name: 'Cancel order' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Record payment' })).toBeInTheDocument()
  })

  it('offers no actions once the order is delivered or cancelled', async () => {
    api(PROFILE_OWNER, {
      detail: detail({
        order: row({ status: 'Delivered', payment_status: 'Paid' }),
        next_status: null,
        can_edit: false,
        can_cancel: false,
        can_pay: false,
      }),
    })
    renderApp('/orders/o1')
    await screen.findByRole('heading', { name: /Order ORD-0001/ })
    for (const n of [/^Mark /, 'Record payment', 'Cancel order', 'Edit'])
      expect(screen.queryByRole('button', { name: n })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Edit/ })).not.toBeInTheDocument()
  })

  it('records a payment and shows an overpayment refusal from the server', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER, {
      paymentReply: {
        status: 422,
        body: {
          error: { code: 'overpayment', message: 'That is more than the outstanding amount.' },
        },
      },
    })
    renderApp('/orders/o1')
    await user.click(await screen.findByRole('button', { name: 'Record payment' }))
    const dlg = screen.getByRole('dialog')
    await user.type(within(dlg).getByLabelText(/Amount/), '999')
    await user.click(within(dlg).getByRole('button', { name: 'Save payment' }))
    expect(
      await within(dlg).findByText('That is more than the outstanding amount.'),
    ).toBeInTheDocument()
    const sent = JSON.parse(String(calls.find((c) => c.url === '/orders/o1/payments')!.data))
    expect(sent).toMatchObject({ amount: '999', method: 'Cash' })
    expect(sent.client_key).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('rejects a malformed amount before sending', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/orders/o1')
    await user.click(await screen.findByRole('button', { name: 'Record payment' }))
    const dlg = screen.getByRole('dialog')
    await user.type(within(dlg).getByLabelText(/Amount/), '-5')
    await user.click(within(dlg).getByRole('button', { name: 'Save payment' }))
    expect(await within(dlg).findByText(/Enter an amount such as/)).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/orders/o1/payments')).toBe(false)
  })
})

describe('Customers', () => {
  it('lists customers and opens one with its order history', async () => {
    const user = userEvent.setup()
    api(PROFILE_BRANCH)
    renderApp('/customers')
    await user.click(await screen.findByRole('link', { name: 'Aisha Khan' }))
    expect(await screen.findByRole('heading', { name: 'Aisha Khan', level: 1 })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'ORD-0001' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Edit/ })).toBeInTheDocument()
  })

  it('searches by name or mobile through the server', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_BRANCH)
    renderApp('/customers')
    await screen.findByRole('link', { name: 'Aisha Khan' })
    await user.type(screen.getByRole('searchbox', { name: 'Search customers' }), '0501')
    await waitFor(() =>
      expect(calls.filter((c) => c.url === '/customers').at(-1)!.params).toMatchObject({
        q: '0501',
      }),
    )
  })

  it('shows the duplicate-mobile message when adding a customer', async () => {
    const user = userEvent.setup()
    api(PROFILE_BRANCH, {
      customerReply: {
        status: 409,
        body: {
          error: {
            code: 'duplicate_customer',
            message: 'This mobile number already belongs to Aisha Khan.',
          },
        },
      },
    })
    renderApp('/customers')
    await user.click(await screen.findByRole('button', { name: /New customer/ }))
    const dlg = screen.getByRole('dialog')
    await user.type(within(dlg).getByLabelText(/Customer name/), 'Another')
    await user.type(within(dlg).getByLabelText(/Mobile number/), '0501234567')
    await user.click(within(dlg).getByRole('button', { name: 'Add customer' }))
    expect(await within(dlg).findByText(/already belongs to Aisha Khan/)).toBeInTheDocument()
  })
})

describe('Pickup & delivery operations', () => {
  it('shows view counts and loads the chosen view for the chosen date', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/order-operations')
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /Processing/ })).toHaveTextContent('4'),
    )
    await user.click(screen.getByRole('tab', { name: /Processing/ }))
    await waitFor(() =>
      expect(calls.some((c) => c.url === '/order-operations/processing')).toBe(true),
    )
    expect(await screen.findByRole('link', { name: 'ORD-0001' })).toBeInTheDocument()
    await user.type(screen.getByRole('searchbox', { name: 'Search' }), 'Aisha')
    await waitFor(() =>
      expect(
        calls.filter((c) => c.url === '/order-operations/processing').at(-1)!.params,
      ).toMatchObject({ q: 'Aisha' }),
    )
  })

  it('updates an order to its next status from the schedule', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/order-operations')
    await user.click(await screen.findByRole('button', { name: 'Mark ORD-0001 Picked Up' }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('ORD-0001 marked Picked Up'))
    expect(calls.some((c) => c.url === '/orders/o1/status')).toBe(true)
  })
})

describe('Order reports', () => {
  it('shows the report, its notes and exports through the server', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_BRANCH)
    renderApp('/order-reports')
    expect(await screen.findByRole('cell', { name: 'Revenue' })).toBeInTheDocument()
    expect(
      screen.getByText('Order revenue is separate from Daily Reports sales.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Branch' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Export CSV/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1))
    const exp = calls.find((c) => c.url === '/orders/reports/order_summary/export')!
    expect(exp.params).toMatchObject({ format: 'csv' })
    expect(exp.params).not.toHaveProperty('branch_id')
    expect(exp.responseType).toBe('blob')
  })
})
