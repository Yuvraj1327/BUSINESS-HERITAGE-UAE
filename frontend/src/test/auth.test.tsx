import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '@/lib/api-client'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import { PROFILE_OWNER, apiError, renderApp, stubApi } from '@/test/render-app'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))

type Fake = ReturnType<typeof createFakeSupabase>
let sb: Fake

beforeEach(() => {
  sb = createFakeSupabase()
  fake.current = sb
  stubApi(() => ({ status: 200, body: PROFILE_OWNER }))
})

const type = userEvent.setup

describe('session restoration and route protection', () => {
  it('redirects an unauthenticated visitor to the login page', async () => {
    const { router } = renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.state).toEqual({ from: '/' })
  })

  it('shows a loading state, never the login form, while the session is restored', async () => {
    let release!: () => void
    sb.state.getSessionGate = new Promise<void>((r) => (release = r))
    sb.state.session = makeSession()
    renderApp('/')
    expect(screen.getByText('Restoring your session…')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument()
    release()
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument()
  })

  it('restores an existing session and sends the bearer token to the API', async () => {
    sb.state.session = makeSession()
    const calls = stubApi(() => ({ status: 200, body: PROFILE_OWNER }))
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    const call = calls.find((c) => c.url === '/auth/profile')
    expect(call?.headers.get('Authorization')).toBe('Bearer access-token-for-tests')
  })

  it('sends a signed-in user away from the login page', async () => {
    sb.state.session = makeSession()
    const { router } = renderApp('/login')
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(router.state.location.pathname).toBe('/')
  })

  it('returns to the originally requested page after sign-in', async () => {
    const { router } = renderApp('/system-status')
    await screen.findByRole('heading', { name: 'Sign in' })
    const user = type()
    await user.type(screen.getByLabelText('Email'), 'person@example.test')
    await user.type(screen.getByLabelText('Password'), 'Secret12345')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/system-status'))
  })
})

describe('login', () => {
  it('validates required fields before calling Supabase', async () => {
    renderApp('/login')
    await screen.findByRole('heading', { name: 'Sign in' })
    await type().click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter your email address')).toBeInTheDocument()
    expect(screen.getByText('Enter your password')).toBeInTheDocument()
    expect(sb.auth.signInWithPassword).not.toHaveBeenCalled()
  })

  it('rejects a malformed email', async () => {
    renderApp('/login')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'not-an-email')
    await user.type(screen.getByLabelText('Password'), 'x')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
  })

  it('signs in with valid credentials and lands in the app', async () => {
    renderApp('/login')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'person@example.test')
    await user.type(screen.getByLabelText('Password'), 'Secret12345')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(sb.auth.signInWithPassword).toHaveBeenCalledWith({
      email: 'person@example.test',
      password: 'Secret12345',
    })
  })

  it('shows one generic message for wrong credentials', async () => {
    sb.auth.signInWithPassword.mockResolvedValueOnce({
      data: { session: null, user: null },
      error: {
        name: 'AuthApiError',
        code: 'invalid_credentials',
        status: 400,
        message: 'Invalid login credentials',
      },
    } as never)
    renderApp('/login')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'person@example.test')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('disables the button while signing in', async () => {
    let finish!: () => void
    sb.auth.signInWithPassword.mockImplementationOnce(
      () =>
        new Promise(
          (r) =>
            (finish = () =>
              r({
                data: { session: null, user: null },
                error: { code: 'invalid_credentials', status: 400, message: 'x' },
              } as never)),
        ),
    )
    renderApp('/login')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'a@b.test')
    await user.type(screen.getByLabelText('Password'), 'pw')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('button', { name: 'Signing in…' })).toBeDisabled()
    finish()
    await screen.findByRole('alert')
  })

  it('toggles password visibility', async () => {
    renderApp('/login')
    const field = await screen.findByLabelText('Password')
    expect(field).toHaveAttribute('type', 'password')
    await type().click(screen.getByRole('button', { name: 'Show password' }))
    expect(field).toHaveAttribute('type', 'text')
    await type().click(screen.getByRole('button', { name: 'Hide password' }))
    expect(field).toHaveAttribute('type', 'password')
  })

  it('has no registration link or route', async () => {
    renderApp('/login')
    await screen.findByRole('heading', { name: 'Sign in' })
    expect(screen.queryByText(/sign up|register|create account/i)).not.toBeInTheDocument()
    const { router } = renderApp('/register')
    expect(router.state.matches.at(-1)?.route.path).toBe('*')
  })

  it('remember-me unchecked keeps the session in sessionStorage only', async () => {
    const { authStorage, setRememberSession } = await import('@/lib/auth-storage')
    setRememberSession(false)
    authStorage.setItem('k', 'v')
    expect(sessionStorage.getItem('k')).toBe('v')
    expect(localStorage.getItem('k')).toBeNull()
    setRememberSession(true)
    authStorage.setItem('k', 'v2')
    expect(localStorage.getItem('k')).toBe('v2')
    expect(sessionStorage.getItem('k')).toBeNull()
    authStorage.removeItem('k')
    expect(authStorage.getItem('k')).toBeNull()
  })

  it('passes the remember choice to the storage layer on sign-in', async () => {
    renderApp('/login')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'a@b.test')
    await user.type(screen.getByLabelText('Password'), 'pw')
    await user.click(screen.getByLabelText('Keep me signed in on this device'))
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(localStorage.getItem('alsafa-auth-remember')).toBe('0')
  })
})

describe('logout and expired sessions', () => {
  it('signs out locally, clears cached data and returns to login', async () => {
    sb.state.session = makeSession()
    const { queryClient, router } = renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    queryClient.setQueryData(['secret'], 1)
    await type().click(screen.getByRole('button', { name: /sign out/i }))
    await type().click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Sign out' }),
    )
    await screen.findByRole('heading', { name: 'Sign in' })
    expect(sb.auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
    expect(queryClient.getQueryData(['secret'])).toBeUndefined()
    expect(router.state.location.pathname).toBe('/login')
    expect(screen.queryByText(/session has ended/i)).not.toBeInTheDocument()
  })

  it('a 401 from the API ends the session and explains why', async () => {
    sb.state.session = makeSession()
    let n = 0
    stubApi(() =>
      n++ === 0 ? { status: 200, body: PROFILE_OWNER } : apiError(401, 'token_expired'),
    )
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    await apiClient.get('/anything').catch(() => undefined)
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByText(/session has ended/i)).toBeInTheDocument()
  })

  it('a refresh failure (SIGNED_OUT from Supabase) shows the session-ended notice', async () => {
    sb.state.session = makeSession()
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    sb.emit('SIGNED_OUT', null)
    expect(await screen.findByText(/session has ended/i)).toBeInTheDocument()
  })

  it('a refreshed token keeps the user in place and re-reads permissions in the background', async () => {
    sb.state.session = makeSession()
    const calls = stubApi(() => ({ status: 200, body: PROFILE_OWNER }))
    renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    sb.emit('TOKEN_REFRESHED', { ...makeSession(), access_token: 'new-token' })
    await waitFor(() => expect(calls.filter((c) => c.url === '/auth/profile')).toHaveLength(2))
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument() // no loading screen in between
    expect(screen.queryByText('Loading your account…')).not.toBeInTheDocument()
  })
})

describe('profile gating', () => {
  async function denied(code: string, status: number) {
    sb.state.session = makeSession()
    stubApi(() => apiError(status, code))
    renderApp('/')
  }

  it('blocks a user without a profile', async () => {
    await denied('profile_missing', 403)
    expect(await screen.findByText('Account not set up')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Dashboard' })).not.toBeInTheDocument()
  })

  it('blocks an inactive user', async () => {
    await denied('account_inactive', 403)
    expect(await screen.findByText('Account inactive')).toBeInTheDocument()
  })

  it('offers a retry when the profile cannot be loaded', async () => {
    await denied('internal_error', 500)
    expect(await screen.findByText('Could not load your account')).toBeInTheDocument()
    stubApi(() => ({ status: 200, body: PROFILE_OWNER }))
    await type().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('lets a blocked user sign out', async () => {
    await denied('account_inactive', 403)
    await type().click(await screen.findByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})

describe('forgot password', () => {
  it('validates the email', async () => {
    renderApp('/forgot-password')
    await type().click(await screen.findByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText('Enter your email address')).toBeInTheDocument()
    expect(sb.auth.resetPasswordForEmail).not.toHaveBeenCalled()
  })

  it('requests a reset with a redirect to /reset-password and shows a neutral confirmation', async () => {
    renderApp('/forgot-password')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'person@example.test')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('status')).toHaveTextContent(/if an account exists/i)
    expect(sb.auth.resetPasswordForEmail).toHaveBeenCalledWith('person@example.test', {
      redirectTo: `${window.location.origin}/reset-password`,
    })
  })

  it('shows the same confirmation when the account does not exist', async () => {
    sb.auth.resetPasswordForEmail.mockResolvedValueOnce({
      data: {},
      error: { name: 'AuthApiError', code: 'user_not_found', status: 400, message: 'x' },
    })
    renderApp('/forgot-password')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'nobody@example.test')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('status')).toHaveTextContent(/if an account exists/i)
  })

  it('reports rate limiting', async () => {
    sb.auth.resetPasswordForEmail.mockResolvedValueOnce({
      data: {},
      error: {
        name: 'AuthApiError',
        code: 'over_email_send_rate_limit',
        status: 429,
        message: 'x',
      },
    })
    renderApp('/forgot-password')
    const user = type()
    await user.type(await screen.findByLabelText('Email'), 'a@b.test')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/too many attempts/i)
  })
})

describe('reset password', () => {
  const recovery = () => {
    sb.state.session = makeSession()
  }
  async function openRecovery() {
    recovery()
    const r = renderApp('/reset-password')
    await screen.findByRole('heading', { name: 'Choose a new password' })
    sb.emit('PASSWORD_RECOVERY', sb.state.session)
    return r
  }

  it('shows an invalid-link page without a recovery session', async () => {
    renderApp('/reset-password')
    expect(await screen.findByText('Reset link not valid')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Request a new link' })).toHaveAttribute(
      'href',
      '/forgot-password',
    )
  })

  it('enforces the password policy', async () => {
    await openRecovery()
    const user = type()
    await user.type(screen.getByLabelText('New password'), 'short1')
    await user.type(screen.getByLabelText('Confirm new password'), 'short1')
    await user.click(screen.getByRole('button', { name: 'Update password' }))
    expect(await screen.findByText('Use at least 10 characters')).toBeInTheDocument()
    expect(sb.auth.updateUser).not.toHaveBeenCalled()
  })

  it.each([
    ['Onlyletterspassword', 'Include at least one number'],
    ['1234567890123', 'Include a lower case letter'],
    ['onlyletters123', 'Include an upper case letter'],
  ])('rejects %s', async (pw, message) => {
    await openRecovery()
    const user = type()
    await user.type(screen.getByLabelText('New password'), pw)
    await user.type(screen.getByLabelText('Confirm new password'), pw)
    await user.click(screen.getByRole('button', { name: 'Update password' }))
    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  it('requires matching passwords', async () => {
    await openRecovery()
    const user = type()
    await user.type(screen.getByLabelText('New password'), 'GoodPassw0rd1')
    await user.type(screen.getByLabelText('Confirm new password'), 'GoodPassw0rd2')
    await user.click(screen.getByRole('button', { name: 'Update password' }))
    expect(await screen.findByText('Passwords do not match')).toBeInTheDocument()
  })

  it('does not let a recovery session into the app', async () => {
    sb.state.session = makeSession()
    const { router } = renderApp('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    sb.emit('PASSWORD_RECOVERY', sb.state.session)
    await waitFor(() => expect(router.state.location.pathname).toBe('/reset-password'))
  })

  it('updates the password, ends the recovery session and returns to login', async () => {
    const { router } = await openRecovery()
    const user = type()
    await user.type(screen.getByLabelText('New password'), 'GoodPassw0rd1')
    await user.type(screen.getByLabelText('Confirm new password'), 'GoodPassw0rd1')
    await user.click(screen.getByRole('button', { name: 'Update password' }))
    expect(await screen.findByText(/password has been updated/i)).toBeInTheDocument()
    expect(sb.auth.updateUser).toHaveBeenCalledWith({ password: 'GoodPassw0rd1' })
    expect(sb.auth.signOut).toHaveBeenCalled()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('shows a friendly error when Supabase rejects the new password', async () => {
    sb.auth.updateUser.mockResolvedValueOnce({
      data: {},
      error: { name: 'AuthApiError', code: 'same_password', status: 422, message: 'x' },
    })
    await openRecovery()
    const user = type()
    await user.type(screen.getByLabelText('New password'), 'GoodPassw0rd1')
    await user.type(screen.getByLabelText('Confirm new password'), 'GoodPassw0rd1')
    await user.click(screen.getByRole('button', { name: 'Update password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/different from your current/i)
  })
})
