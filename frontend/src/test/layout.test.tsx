import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildBreadcrumbs } from '@/lib/breadcrumbs'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  alertSummary,
  BRANCH_VIEW_EMPTY,
  OWNER_DASHBOARD,
  PROFILE_BRANCH,
  PROFILE_OWNER,
  renderApp,
  stubApi,
} from '@/test/render-app'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

/** jsdom has no layout engine: emulate the three breakpoints through matchMedia (min-width queries). */
function setViewport(width: number) {
  window.matchMedia = ((query: string) => {
    const min = Number(/min-width:\s*(\d+)px/.exec(query)?.[1] ?? 0)
    return {
      matches: width >= min,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    } as MediaQueryList
  }) as typeof window.matchMedia
}

const TEST_BRANCHES = [
  { id: 'b1', name: 'Test Branch One', sort_order: 1, is_active: true },
  { id: 'b2', name: 'Test Branch Two', sort_order: 2, is_active: true },
]
const apiFor = (profile: object) =>
  stubApi((c) => {
    if (c.url === '/branches') return { status: 200, body: TEST_BRANCHES }
    if (c.url === '/dashboard/owner') return { status: 200, body: OWNER_DASHBOARD }
    if (c.url === '/branch-date-view') return { status: 200, body: BRANCH_VIEW_EMPTY }
    if (c.url === '/alerts/summary') return { status: 200, body: alertSummary() }
    if (c.url === '/users') return { status: 200, body: [] }
    return { status: 200, body: profile }
  })

const nav = () => screen.getByRole('navigation', { name: 'Main' })
const linkNames = () =>
  within(nav())
    .getAllByRole('link')
    .map((a) => a.textContent)
const dashboard = () => screen.findByRole('heading', { name: 'Dashboard', level: 1 })

beforeEach(() => {
  const sb = createFakeSupabase()
  fake.current = sb
  sb.state.session = makeSession()
  setViewport(1440)
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
})

describe('navigation structure and permissions', () => {
  it('owner sees every section and module in the specified order', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/')
    await dashboard()
    const labels = within(nav())
      .getAllByRole('group')
      .map((g) => g.getAttribute('aria-labelledby'))
    expect(labels).toHaveLength(9)
    for (const section of [
      'Overview',
      'Operations',
      'Orders & Delivery',
      'Finance',
      'People & Compliance',
      'Property',
      'Management',
      'Administration',
      'Account',
    ]) {
      expect(within(nav()).getByText(section)).toBeInTheDocument()
    }
    expect(linkNames()).toEqual(
      expect.arrayContaining([
        'Dashboard',
        'Branch Management',
        'Branch & Date View',
        'Daily Reports',
        'Order Management',
        'Customers',
        'Cash & Banks',
        'Suppliers',
        'Employees',
        'Rental Agreements',
        'PDC Cheques',
        'Tasks',
        'Notifications',
        'Reports & Analytics',
        'Activity History',
        'User Management',
      ]),
    )
    expect(linkNames()).not.toContain('My Branch')
    expect(within(nav()).getByRole('button', { name: 'Settings' })).toBeInTheDocument()
  })

  it('branch user sees only Overview and Operations with their own modules', async () => {
    apiFor(PROFILE_BRANCH)
    renderApp('/')
    await dashboard()
    expect(linkNames()).toEqual([
      'Dashboard',
      'My Branch',
      'Branch & Date View',
      'Daily Reports',
      'Order Management',
      'Orders',
      'Customers',
      'Pickup & Delivery',
      'Order Reports',
    ])
    for (const hidden of [
      'Finance',
      'People & Compliance',
      'Property',
      'Management',
      'Administration',
    ]) {
      expect(within(nav()).queryByText(hidden)).not.toBeInTheDocument()
    }
    // Settings is self-service (every user), but its Owner-only "System status" page is not offered.
    const settings = within(nav()).getByRole('button', { name: 'Settings' })
    await userEvent.setup().click(settings)
    for (const page of [
      'My Profile',
      'Account & Security',
      'Appearance',
      'Notifications',
      'Preferences',
      'About',
    ]) {
      expect(within(nav()).getByRole('link', { name: page })).toBeInTheDocument()
    }
    expect(within(nav()).queryByRole('link', { name: 'System status' })).not.toBeInTheDocument()
  })

  it('a user with no grants sees no navigation entries at all (default deny)', async () => {
    apiFor({
      ...PROFILE_BRANCH,
      permissions: { dashboard: { actions: ['read'], scope: 'own_branch' } },
    })
    renderApp('/')
    await dashboard()
    expect(linkNames()).toEqual(['Dashboard'])
  })

  it('the Settings group expands to its pages and marks the active one', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/system-status')
    await screen.findByText('Application foundation')
    const group = within(nav()).getByRole('button', { name: 'Settings' })
    expect(group).toHaveAttribute('aria-expanded', 'true')
    expect(within(nav()).getByRole('link', { name: 'System status' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    await userEvent.setup().click(group)
    expect(group).toHaveAttribute('aria-expanded', 'false')
    expect(within(nav()).queryByRole('link', { name: 'System status' })).not.toBeInTheDocument()
  })

  it('marks the current page in the navigation', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/users')
    await screen.findByText('No users found')
    expect(within(nav()).getByRole('link', { name: 'User Management' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(nav()).getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute(
      'aria-current',
    )
  })
})

describe('role layouts', () => {
  it('owner has the global branch selector fed by the API and shares the choice with the dashboard', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/')
    await dashboard()
    const selector = await screen.findByRole('combobox', { name: 'Branch' })
    await waitFor(() => expect(selector).toBeEnabled())
    expect(selector).toHaveTextContent('All branches')
    const user = userEvent.setup()
    await user.click(selector)
    await user.click(await screen.findByRole('option', { name: 'Test Branch Two' }))
    expect(selector).toHaveTextContent('Test Branch Two')
  })

  it('branch user has no branch selector, sees the assigned branch and never requests the branch list', async () => {
    const calls = apiFor(PROFILE_BRANCH)
    renderApp('/')
    await dashboard()
    expect(screen.queryByRole('combobox', { name: 'Branch' })).not.toBeInTheDocument()
    expect(screen.getByTitle('Your assigned branch')).toHaveTextContent('SATWA')
    expect(screen.getByText('Assigned branch')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/branches')).toBe(false)
  })

  it('owner dashboard shows figures from the API and an honest not-configured state', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/')
    await dashboard()
    expect(await screen.findByText(/AED\s?1,500\.00/)).toBeInTheDocument()
    expect(screen.getByText('Needs attention')).toBeInTheDocument()
    expect(
      screen.getByText(/Not configured: balances need the opening balances/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Reporting start date not configured/)).toBeInTheDocument()
  })

  it('branch dashboard offers report entry only with the create permission', async () => {
    apiFor(PROFILE_BRANCH)
    renderApp('/')
    await dashboard()
    expect(await screen.findByRole('link', { name: /Submit daily report/ })).toBeInTheDocument()
  })
})

describe('admin pages and protected routes', () => {
  it('a permitted admin page opens inside the shell', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/users')
    expect(
      await screen.findByRole('heading', { name: 'User Management', level: 1 }),
    ).toBeInTheDocument()
    expect(await screen.findByText('No users found')).toBeInTheDocument()
  })

  it.each(['/suppliers', '/cash-banks', '/users', '/system-status', '/tasks'])(
    'branch user typing %s sees Access denied inside the shell',
    async (path) => {
      apiFor(PROFILE_BRANCH)
      renderApp(path)
      expect(await screen.findByText('Access denied')).toBeInTheDocument()
      expect(screen.queryByText('No users found')).not.toBeInTheDocument()
      expect(nav()).toBeInTheDocument() // the shell stays usable
    },
  )

  it('unknown URL shows the 404 page inside the shell for a signed-in user', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/nope/nothing')
    expect(await screen.findByRole('link', { name: 'Back to start' })).toBeInTheDocument()
    expect(nav()).toBeInTheDocument()
  })

  it('unknown URL for a signed-out visitor shows the bare 404 (no shell, no data calls)', async () => {
    const sb = createFakeSupabase()
    fake.current = sb
    const calls = stubApi(() => ({ status: 200, body: PROFILE_OWNER }))
    renderApp('/nope')
    expect((await screen.findAllByText('Page not found')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })
})

describe('breadcrumbs', () => {
  it('builds Home → section → page from the navigation definition', () => {
    expect(buildBreadcrumbs('/')).toEqual([{ label: 'Dashboard' }])
    expect(buildBreadcrumbs('/daily-reports')).toEqual([
      { label: 'Dashboard', to: '/' },
      { label: 'Operations' },
      { label: 'Daily Reports' },
    ])
    expect(buildBreadcrumbs('/system-status/').map((c) => c.label)).toEqual([
      'Dashboard',
      'Account',
      'Settings',
      'System status',
    ])
    expect(buildBreadcrumbs('/zzz').map((c) => c.label)).toEqual(['Dashboard', 'Page not found'])
  })

  it('shows the current page as the last crumb with aria-current', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/cash-banks')
    const crumbs = await screen.findByRole('navigation', { name: 'Breadcrumb' })
    expect(within(crumbs).getByText('Finance')).toBeInTheDocument()
    expect(within(crumbs).getByText('Cash & Banks')).toHaveAttribute('aria-current', 'page')
    expect(within(crumbs).getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/')
    expect(document.title).toBe('Cash & Banks · ALSAFA Heritage Laundry')
  })
})

describe('responsive behaviour', () => {
  it('desktop sidebar collapses to a rail and remembers the choice', async () => {
    apiFor(PROFILE_OWNER)
    const user = userEvent.setup()
    const view = renderApp('/')
    await dashboard()
    expect(within(nav()).getByText('Operations')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(within(nav()).queryByText('Operations')).not.toBeInTheDocument()
    // Labels survive for screen readers and keyboard users.
    expect(within(nav()).getByRole('link', { name: 'Daily Reports' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(localStorage.getItem('alsafa.sidebar.collapsed')).toBe('1')
    view.unmount()

    renderApp('/')
    await dashboard()
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument()
  })

  it('rail links keep their styling and active state (tooltip trigger must not mangle the className)', async () => {
    apiFor(PROFILE_OWNER)
    localStorage.setItem('alsafa.sidebar.collapsed', '1')
    renderApp('/users')
    await screen.findByText('No users found')
    const active = within(nav()).getByRole('link', { name: 'User Management' })
    expect(active.className).not.toMatch(/=>|function|\{/)
    expect(active).toHaveClass('justify-center', 'bg-sidebar-accent')
    expect(within(nav()).getByRole('link', { name: 'Dashboard' })).not.toHaveClass(
      'bg-sidebar-accent',
    )
  })

  it('collapsed rail shows a tooltip with the page name on keyboard focus', async () => {
    apiFor(PROFILE_OWNER)
    localStorage.setItem('alsafa.sidebar.collapsed', '1')
    renderApp('/')
    await dashboard()
    within(nav()).getByRole('link', { name: 'Suppliers' }).focus()
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Suppliers')
  })

  it('tablet starts as an icon rail and opens the full navigation as a drawer', async () => {
    setViewport(800)
    apiFor(PROFILE_OWNER)
    const user = userEvent.setup()
    renderApp('/')
    await dashboard()
    expect(within(nav()).queryByText('Operations')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    const drawer = await screen.findByRole('dialog')
    expect(within(drawer).getByText('Operations')).toBeInTheDocument()
  })

  it('mobile has no fixed sidebar; the drawer opens, navigates and closes itself', async () => {
    setViewport(390)
    apiFor(PROFILE_OWNER)
    const user = userEvent.setup()
    renderApp('/')
    await dashboard()
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    const drawer = await screen.findByRole('dialog')
    await user.click(within(drawer).getByRole('link', { name: 'Suppliers' }))
    expect(await screen.findByRole('heading', { name: 'Suppliers', level: 1 })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('Escape closes the mobile drawer and returns focus to the toggle', async () => {
    setViewport(390)
    apiFor(PROFILE_BRANCH)
    const user = userEvent.setup()
    renderApp('/')
    await dashboard()
    const toggle = screen.getByRole('button', { name: 'Open navigation' })
    await user.click(toggle)
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(toggle).toHaveFocus())
  })

  it('mobile shows the branch selector in its own row for an owner', async () => {
    setViewport(390)
    apiFor(PROFILE_OWNER)
    renderApp('/')
    await dashboard()
    expect(await screen.findByRole('combobox', { name: 'Branch' })).toBeInTheDocument()
  })
})

describe('header menus', () => {
  it('user menu shows the account and signs out', async () => {
    apiFor(PROFILE_BRANCH)
    const user = userEvent.setup()
    renderApp('/')
    await dashboard()
    await user.click(screen.getByRole('button', { name: 'Account menu for Test Branch User' }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByText('Branch User · SATWA')).toBeInTheDocument()
    await user.click(within(menu).getByRole('menuitem', { name: 'Sign out' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Sign out' }),
    )
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('notification menu is honest about having nothing to show', async () => {
    apiFor(PROFILE_OWNER)
    const user = userEvent.setup()
    renderApp('/')
    await dashboard()
    await user.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(await screen.findByText('You have no notifications.')).toBeInTheDocument()
  })

  it('skip link targets the main content', async () => {
    apiFor(PROFILE_OWNER)
    renderApp('/')
    await dashboard()
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute(
      'href',
      '#main-content',
    )
    expect(document.getElementById('main-content')).toBeInTheDocument()
  })
})
