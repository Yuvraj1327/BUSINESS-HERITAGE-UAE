import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Can } from '@/auth/permission-guards'
import { hasPermission, scopeOf } from '@/auth/permissions'
import { apiClient } from '@/lib/api-client'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import {
  PROFILE_BRANCH,
  PROFILE_OWNER,
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

type Fake = ReturnType<typeof createFakeSupabase>
let sb: Fake

beforeEach(() => {
  sb = createFakeSupabase()
  fake.current = sb
  sb.state.session = makeSession()
})

const nav = () => screen.getByRole('navigation', { name: 'Main' })

describe('permission helpers (default deny)', () => {
  const perms = { daily_reports: { actions: ['read', 'create'], scope: 'own_branch' as const } }
  it('grants only what the server listed', () => {
    expect(hasPermission(perms, 'daily_reports', 'read')).toBe(true)
    expect(hasPermission(perms, 'daily_reports', 'create')).toBe(true)
    expect(hasPermission(perms, 'daily_reports', 'update')).toBe(false)
    expect(hasPermission(perms, 'suppliers', 'read')).toBe(false)
    expect(scopeOf(perms, 'daily_reports')).toBe('own_branch')
    expect(scopeOf(perms, 'suppliers')).toBeNull()
  })
  it('denies everything without permissions', () => {
    expect(hasPermission(null, 'dashboard', 'read')).toBe(false)
    expect(hasPermission(undefined, 'dashboard', 'read')).toBe(false)
    expect(hasPermission({}, 'dashboard', 'read')).toBe(false)
  })
})

describe('navigation and route protection', () => {
  it('owner sees the administrative modules', async () => {
    stubApi(() => ({ status: 200, body: PROFILE_OWNER }))
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(within(nav()).getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    await userEvent.setup().click(within(nav()).getByRole('button', { name: 'Settings' }))
    expect(within(nav()).getByRole('link', { name: 'System status' })).toBeInTheDocument()
  })

  it('branch user sees only the modules the server granted', async () => {
    stubApi(() => ({ status: 200, body: PROFILE_BRANCH }))
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    const links = within(nav())
      .getAllByRole('link')
      .map((a) => a.textContent)
    expect(links).toEqual([
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
    expect(screen.getAllByText('SATWA').length).toBeGreaterThan(0)
  })

  it('direct URL to an owner-only page shows Access denied to a branch user', async () => {
    stubApi(() => ({ status: 200, body: PROFILE_BRANCH }))
    const { router } = renderApp('/system-status')
    expect(await screen.findByText('Access denied')).toBeInTheDocument()
    expect(screen.queryByText('Application foundation')).not.toBeInTheDocument()
    expect(screen.queryByText('Backend API')).not.toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/system-status')
  })

  it('direct URL works for the owner', async () => {
    stubApi((c) =>
      c.url === '/auth/profile'
        ? { status: 200, body: PROFILE_OWNER }
        : { status: 200, body: { status: 'ok', service: 's', version: '1', environment: 'test' } },
    )
    renderApp('/system-status')
    expect(await screen.findByText('Application foundation')).toBeInTheDocument()
  })

  it('shows no flicker of restricted content while the profile loads', async () => {
    let release!: (r: ApiReply) => void
    const gate = new Promise<ApiReply>((r) => (release = r))
    apiClient.defaults.adapter = async (config) => {
      const r = await gate
      return { data: r.body, status: r.status, statusText: '', headers: {}, config }
    }
    renderApp('/system-status')
    expect(await screen.findByText('Loading your account…')).toBeInTheDocument()
    expect(screen.queryByText('Access denied')).not.toBeInTheDocument()
    expect(screen.queryByText('Application foundation')).not.toBeInTheDocument()
    release({ status: 200, body: PROFILE_BRANCH })
    expect(await screen.findByText('Access denied')).toBeInTheDocument()
  })

  it('unknown URLs are 404, not Access denied', async () => {
    stubApi(() => ({ status: 200, body: PROFILE_BRANCH }))
    renderApp('/no-such-page')
    expect((await screen.findAllByText('Page not found')).length).toBeGreaterThan(0)
    expect(screen.queryByText('Access denied')).not.toBeInTheDocument()
  })

  it('an existing but forbidden module URL shows Access denied', async () => {
    stubApi(() => ({ status: 200, body: PROFILE_BRANCH }))
    renderApp('/users')
    expect(await screen.findByText('Access denied')).toBeInTheDocument()
  })
})

describe('permission-based rendering', () => {
  async function renderCan(profile: typeof PROFILE_OWNER | typeof PROFILE_BRANCH) {
    stubApi(() => ({ status: 200, body: profile }))
    const { AuthProvider } = await import('@/auth/AuthProvider')
    const { QueryClientProvider, QueryClient } = await import('@tanstack/react-query')
    const { render } = await import('@testing-library/react')
    const { useAuth } = await import('@/auth/use-auth')
    function Gate() {
      const { profileStatus } = useAuth()
      return profileStatus === 'ready' ? (
        <Can module="user_management" action="manage" fallback={<span>no-admin</span>}>
          <button>Deactivate user</button>
        </Can>
      ) : (
        <span>loading</span>
      )
    }
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider>
          <Gate />
        </AuthProvider>
      </QueryClientProvider>,
    )
  }

  it('renders restricted actions for the owner only', async () => {
    await renderCan(PROFILE_OWNER)
    expect(await screen.findByRole('button', { name: 'Deactivate user' })).toBeInTheDocument()
  })

  it('does not render restricted actions for a branch user', async () => {
    await renderCan(PROFILE_BRANCH)
    expect(await screen.findByText('no-admin')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Deactivate user' })).not.toBeInTheDocument()
  })
})

describe('changes while signed in', () => {
  it('a role downgrade is picked up on token refresh without a loading flash', async () => {
    let profile: object = PROFILE_OWNER
    stubApi(() => ({ status: 200, body: profile }))
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    await userEvent.setup().click(within(nav()).getByRole('button', { name: 'Settings' }))
    expect(within(nav()).getByRole('link', { name: 'System status' })).toBeInTheDocument()
    profile = PROFILE_BRANCH
    sb.emit('TOKEN_REFRESHED', makeSession())
    await waitFor(() =>
      expect(within(nav()).queryByRole('link', { name: 'System status' })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('deactivation discovered on refresh sends the user to the inactive page', async () => {
    let reply: ApiReply = { status: 200, body: PROFILE_BRANCH }
    stubApi(() => reply)
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    reply = apiError(403, 'account_inactive')
    sb.emit('TOKEN_REFRESHED', makeSession())
    expect(await screen.findByText('Account inactive')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Dashboard' })).not.toBeInTheDocument()
  })

  it('a 403 from the API (permission_denied) notifies the user and re-reads permissions', async () => {
    const { toast } = await import('sonner')
    let profileCalls = 0
    const calls = stubApi((c) => {
      if (c.url === '/auth/profile') {
        profileCalls++
        return { status: 200, body: PROFILE_BRANCH }
      }
      return apiError(403, 'permission_denied')
    })
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    await apiClient.get('/users').catch(() => undefined)
    await waitFor(() => expect(profileCalls).toBe(2))
    expect(toast.error).toHaveBeenCalled()
    expect(calls.some((c) => c.url === '/users')).toBe(true)
  })

  it('an expired session still returns to login', async () => {
    let n = 0
    stubApi(() =>
      n++ === 0 ? { status: 200, body: PROFILE_BRANCH } : apiError(401, 'token_expired'),
    )
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    await apiClient.get('/anything').catch(() => undefined)
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('profile 403s do not trigger the generic forbidden handler loop', async () => {
    const calls = stubApi(() => apiError(403, 'account_inactive'))
    renderApp('/')
    expect(await screen.findByText('Account inactive')).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 150))
    expect(calls.filter((c) => c.url === '/auth/profile')).toHaveLength(1)
  })
})

describe('user interaction sanity', () => {
  it('branch user can sign out from the app shell', async () => {
    stubApi(() => ({ status: 200, body: PROFILE_BRANCH }))
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /sign out/i }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Sign out' }),
    )
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})
