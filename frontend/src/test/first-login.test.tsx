import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import { PROFILE_BRANCH, apiError, renderApp, stubApi } from '@/test/render-app'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const TEMP = 'Initial-Pass1'
const NEW = 'My-Own-Passw0rd'

beforeEach(() => {
  const sb = createFakeSupabase()
  fake.current = sb
  sb.state.session = makeSession()
  window.matchMedia ??= (() => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  })) as never
})

function api(changeReply?: { status: number; body: unknown }) {
  let pending = true
  const calls = stubApi((c) => {
    if (c.url === '/auth/change-password') {
      if (changeReply) return changeReply
      pending = false
      return { status: 204, body: null }
    }
    if (c.url === '/auth/profile') {
      return { status: 200, body: { ...PROFILE_BRANCH, must_change_password: pending } }
    }
    return { status: 200, body: [] }
  })
  return calls
}

async function fill(user: ReturnType<typeof userEvent.setup>, current: string, next: string) {
  await user.type(await screen.findByLabelText('Current password'), current)
  await user.type(screen.getByLabelText('New password'), next)
  await user.type(screen.getByLabelText('Confirm new password'), next)
  await user.click(screen.getByRole('button', { name: 'Change password' }))
}

describe('first-login password change', () => {
  it('shows only the change-password page, not the app, while the flag is set', async () => {
    api()
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Change your password' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('refuses a new password equal to the initial one or too weak, without calling the API', async () => {
    const calls = api()
    const user = userEvent.setup()
    renderApp('/')
    await fill(user, TEMP, TEMP)
    expect(await screen.findByText(/different from the one you were given/)).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/auth/change-password')).toBe(false)
  })

  it('changes the password through the backend, then opens the app', async () => {
    const calls = api()
    const user = userEvent.setup()
    renderApp('/')
    await fill(user, TEMP, NEW)
    await waitFor(() => expect(calls.some((c) => c.url === '/auth/change-password')).toBe(true))
    const post = calls.find((c) => c.url === '/auth/change-password')!
    expect(JSON.parse(post.data as string)).toEqual({ new_password: NEW, confirm_password: NEW })
    await waitFor(() =>
      expect(
        screen.queryByRole('heading', { name: 'Change your password' }),
      ).not.toBeInTheDocument(),
    )
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(NEW)
  })

  it('shows the server error when the password is rejected', async () => {
    api(apiError(422, 'validation_error', 'Request validation failed'))
    const user = userEvent.setup()
    renderApp('/')
    await fill(user, TEMP, NEW)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
