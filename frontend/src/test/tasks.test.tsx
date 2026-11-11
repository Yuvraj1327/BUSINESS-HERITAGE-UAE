import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { describeTaskChange, dueText } from '@/pages/tasks/helpers'
import { taskFormSchema } from '@/schemas/tasks'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  PROFILE_BRANCH,
  PROFILE_OWNER,
  alertItem,
  alertSummary,
  apiError,
  renderApp,
  stubApi,
  type ApiReply,
} from '@/test/render-app'

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
const task = (over: Record<string, unknown> = {}) => ({
  id: 't1',
  title: 'Renew water contract',
  description: 'Call the supplier',
  branch_id: 'b1',
  branch_name: 'Test Branch One',
  assignee_id: null,
  assignee_name: 'Unassigned',
  due_date: '2026-11-08',
  status: 'To Do',
  timing: 'overdue',
  days_to_due: -2,
  notes: null,
  created_at: '2026-11-01T08:00:00Z',
  created_by_name: 'Test Owner',
  updated_at: '2026-11-01T08:00:00Z',
  updated_by_name: null,
  completed_at: null,
  completed_by_name: null,
  ...over,
})
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const SUMMARY = { total: 4, to_do: 2, in_progress: 1, done: 1, overdue: 1, due_today: 1, due_7: 2 }
const HISTORY = [
  {
    id: 1,
    occurred_at: '2026-11-01T08:00:00Z',
    actor_name: 'Test Owner',
    action: 'INSERT',
    table_name: 'tasks',
    record_id: 't1',
    reason: null,
    old_values: null,
    new_values: null,
  },
]

interface World {
  tasks: unknown[]
  statusFail: boolean
}
function api(profile: object, over: Partial<World> = {}) {
  const w: World = {
    tasks: [
      task(),
      task({
        id: 't2',
        title: 'Pay trade licence fee',
        timing: 'due_today',
        days_to_due: 0,
        status: 'In Progress',
      }),
    ],
    statusFail: false,
    ...over,
  }
  return stubApi((c): ApiReply => {
    const url = c.url ?? ''
    const method = c.method ?? 'get'
    if (url === '/branches') return { status: 200, body: BRANCHES }
    if (url === '/alerts/summary') return { status: 200, body: alertSummary() }
    if (url === '/tasks/summary') return { status: 200, body: SUMMARY }
    if (url === '/tasks/assignees')
      return {
        status: 200,
        body: [{ id: 'u1', name: 'Test Owner', role: 'owner', branch_name: null }],
      }
    if (url === '/tasks' && method === 'post')
      return { status: 201, body: { task: task(), history: HISTORY } }
    if (url === '/tasks') return { status: 200, body: page(w.tasks) }
    if (url === '/tasks/t1/status') {
      if (w.statusFail) return apiError(409, 'status_unchanged', 'The task is already Done')
      return {
        status: 200,
        body: {
          task: task({
            status: 'Done',
            timing: 'completed',
            completed_at: '2026-11-10T07:00:00Z',
            completed_by_name: 'Test Owner',
          }),
          history: HISTORY,
        },
      }
    }
    if (url === '/tasks/t1') return { status: 200, body: { task: task(), history: HISTORY } }
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
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
})

describe('task helpers and form rules', () => {
  it('describes due text and history from audit rows', () => {
    expect(dueText(-2)).toBe('2 days overdue')
    expect(dueText(0)).toBe('Due today')
    expect(dueText(1)).toBe('Due in 1 day')
    expect(dueText(null)).toBe('')
    expect(
      describeTaskChange({
        id: 2,
        occurred_at: '',
        actor_name: null,
        action: 'UPDATE',
        table_name: 'tasks',
        record_id: 't1',
        reason: null,
        old_values: { status: 'To Do', completed_at: null },
        new_values: { status: 'Done', completed_at: '2026-11-10T07:00:00Z' },
      }),
    ).toBe('Status: To Do → Done; Marked completed')
  })

  it('requires a title', () => {
    const base = {
      title: ' ',
      description: '',
      branch_id: '',
      due_date: '',
      assignee_id: '',
      notes: '',
      reason: '',
    }
    expect(taskFormSchema.safeParse(base).success).toBe(false)
    expect(taskFormSchema.safeParse({ ...base, title: 'x' }).success).toBe(true)
  })
})

describe('Tasks page', () => {
  it('shows the seven summary cards and distinguishes overdue / due today', async () => {
    api(PROFILE_OWNER)
    renderApp('/tasks')
    const cards = await screen.findByLabelText('Task summary')
    for (const label of [
      'Total Tasks',
      'To Do',
      'In Progress',
      'Completed',
      'Overdue',
      'Due Today',
      'Due Within 7 Days',
    ])
      expect(within(cards).getByText(label)).toBeInTheDocument()
    const table = await screen.findByRole('table', { name: 'Tasks' })
    const row = within(table).getByText('Renew water contract').closest('tr')!
    expect(within(row).getByText('Overdue')).toBeInTheDocument()
    expect(within(row).getByText('2 days overdue')).toBeInTheDocument()
    expect(within(row).getByText('Unassigned')).toBeInTheDocument()
    const other = within(table).getByText('Pay trade licence fee').closest('tr')!
    expect(within(other).getByText('Due Today')).toBeInTheDocument()
  })

  it('sends the search, status and view filters to the server', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/tasks?view=overdue')
    await screen.findByRole('table', { name: 'Tasks' })
    expect(calls.some((c) => c.url === '/tasks' && c.params?.view === 'overdue')).toBe(true)
    await user.type(screen.getByLabelText('Search'), 'water')
    await screen.findByRole('table', { name: 'Tasks' })
    expect(calls.some((c) => c.url === '/tasks' && c.params?.q === 'water')).toBe(true)
  })

  it('creates a task and starts it unassigned', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/tasks')
    await user.click(await screen.findByRole('button', { name: /New task/ }))
    const form = await screen.findByRole('form', { name: 'Task' })
    await user.click(within(form).getByRole('button', { name: 'Create task' }))
    expect(await within(form).findByText('Enter a title')).toBeInTheDocument()
    await user.type(within(form).getByLabelText(/Title/), 'Renew water contract')
    await user.click(within(form).getByRole('button', { name: 'Create task' }))
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith('Task created'))
    const post = calls.find((c) => c.method === 'post' && c.url === '/tasks')!
    expect(JSON.parse(post.data as string)).toMatchObject({
      title: 'Renew water contract',
      branch_id: null,
      assignee_id: null,
    })
  })

  it('a Branch User cannot open Tasks and never requests them', async () => {
    const calls = api(PROFILE_BRANCH)
    renderApp('/tasks')
    expect((await screen.findAllByText(/access denied/i)).length).toBeGreaterThan(0)
    expect(calls.some((c) => (c.url ?? '').startsWith('/tasks'))).toBe(false)
  })
})

describe('Task detail', () => {
  it('shows details and history, and marks the task completed', async () => {
    const user = userEvent.setup()
    const calls = api(PROFILE_OWNER)
    renderApp('/tasks/t1')
    expect(
      await screen.findByRole('heading', { name: 'Renew water contract', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText('Task created')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Mark completed/ }))
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith('Task marked completed'))
    expect(calls.find((c) => c.url === '/tasks/t1/status')?.method).toBe('post')
  })

  it('shows the server error when a status change is refused', async () => {
    const user = userEvent.setup()
    api(PROFILE_OWNER, { statusFail: true })
    renderApp('/tasks/t1')
    await user.click(await screen.findByRole('button', { name: /Mark completed/ }))
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith('The task is already Done'))
  })
})

describe('Notification center', () => {
  const ITEMS = [
    alertItem({
      id: 'a1',
      severity: 'critical',
      kind: 'cheque_bounced',
      type_label: 'PDC cheque bounced',
      href: '/pdc-cheques/c9',
    }),
    alertItem({ id: 'a2' }),
  ]
  function alertsApi(profile: object, fail = false) {
    return stubApi((c): ApiReply => {
      const url = c.url ?? ''
      const method = c.method ?? 'get'
      if (url === '/branches') return { status: 200, body: BRANCHES }
      if (url === '/alerts/summary') return { status: 200, body: alertSummary(ITEMS) }
      if (url === '/alerts/facets')
        return {
          status: 200,
          body: { kinds: [['task_overdue', 'Task overdue']], modules: [['tasks', 'Tasks']] },
        }
      if (url === '/alerts' && !fail) return { status: 200, body: page(ITEMS) }
      if (url === '/alerts') return apiError(500, 'internal_error', 'Boom')
      if (url === '/alerts/history')
        return {
          status: 200,
          body: page([
            alertItem({ id: 'a3', status: 'resolved', resolved_at: '2026-11-10T08:00:00Z' }),
          ]),
        }
      if (url === '/alerts/a2/acknowledge' && method === 'post')
        return { status: 200, body: alertItem({ status: 'acknowledged' }) }
      if (url === '/alerts/a2/read' && method === 'post')
        return { status: 200, body: alertItem({ status: 'read' }) }
      return { status: 200, body: profile }
    })
  }

  it('bell shows the unread count and a link to every notification', async () => {
    const user = userEvent.setup()
    alertsApi(PROFILE_OWNER)
    renderApp('/tasks')
    await user.click(await screen.findByRole('button', { name: /Notifications, 2 unread/ }))
    const list = await screen.findByRole('list', { name: 'Alerts' })
    expect(within(list).getByRole('link', { name: /PDC cheque bounced/ })).toHaveAttribute(
      'href',
      '/pdc-cheques/c9',
    )
    expect(screen.getByRole('menuitem', { name: /View all notifications/ })).toHaveAttribute(
      'href',
      '/notifications',
    )
  })

  it('lists active alerts with severity words, links, and acknowledges one', async () => {
    const user = userEvent.setup()
    const calls = alertsApi(PROFILE_OWNER)
    renderApp('/notifications')
    const table = await screen.findByRole('table', { name: 'Active alerts' })
    expect(await within(table).findByText('Critical')).toBeInTheDocument()
    expect(within(table).getByRole('link', { name: 'PDC cheque bounced' })).toHaveAttribute(
      'href',
      '/pdc-cheques/c9',
    )
    await user.click(within(table).getByRole('button', { name: 'Acknowledge: Task overdue' }))
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith('Alert acknowledged'))
    expect(calls.some((c) => c.url === '/alerts/a2/acknowledge' && c.method === 'post')).toBe(true)
  })

  it('switches to the history and shows resolved alerts', async () => {
    const user = userEvent.setup()
    alertsApi(PROFILE_OWNER)
    renderApp('/notifications')
    await screen.findByRole('table', { name: 'Active alerts' })
    await user.click(screen.getByRole('button', { name: 'History' }))
    const table = await screen.findByRole('table', { name: 'Alert history' })
    expect(within(table).getByText('Resolved')).toBeInTheDocument()
  })

  it('shows an error state with retry when alerts cannot load', async () => {
    alertsApi(PROFILE_OWNER, true)
    renderApp('/notifications')
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })

  it('a Branch User has no bell feed and cannot open Notifications', async () => {
    const calls = alertsApi(PROFILE_BRANCH)
    renderApp('/notifications')
    expect((await screen.findAllByText(/access denied/i)).length).toBeGreaterThan(0)
    expect(calls.some((c) => (c.url ?? '').startsWith('/alerts'))).toBe(false)
  })
})
