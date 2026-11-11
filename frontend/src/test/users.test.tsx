import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { userCreateSchema } from '@/schemas/users'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import { PROFILE_BRANCH, PROFILE_OWNER, apiError, renderApp, stubApi } from '@/test/render-app'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const PW = 'Str0ngPassw0rd!'
const BRANCHES = [{ id: 'b1', name: 'Test Branch One', sort_order: 1, is_active: true }]
const USER = {
  user_id: 'u9',
  full_name: 'New Person',
  role: 'branch',
  branch_id: 'b1',
  is_active: true,
  created_at: '2026-11-10T06:00:00Z',
}

function api(profile: object, create?: () => { status: number; body: unknown }) {
  return stubApi((c) => {
    const url = c.url ?? ''
    if (url === '/branches') return { status: 200, body: BRANCHES }
    if (url === '/users') {
      if (c.method === 'post') return create?.() ?? { status: 201, body: USER }
      return { status: 200, body: [] }
    }
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
  window.matchMedia ??= (() => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  })) as never
})

describe('user creation schema', () => {
  it('requires name, valid email and a branch; has no role field', () => {
    const ok = {
      email: 'a@b.co',
      full_name: 'A B',
      branch_id: 'b1',
      password: PW,
      confirm_password: PW,
    }
    expect(userCreateSchema.safeParse(ok).success).toBe(true)
    expect(userCreateSchema.safeParse({ ...ok, confirm_password: PW + 'x' }).success).toBe(false)
    for (const weak of ['short1A', 'alllowercase123', 'ALLUPPERCASE123', 'NoDigitsHereAtAll']) {
      expect(
        userCreateSchema.safeParse({ ...ok, password: weak, confirm_password: weak }).success,
      ).toBe(false)
    }
    expect(userCreateSchema.safeParse({ ...ok, email: 'nope' }).success).toBe(false)
    expect(userCreateSchema.safeParse({ ...ok, branch_id: '' }).success).toBe(false)
    expect(userCreateSchema.safeParse({ ...ok, full_name: '  ' }).success).toBe(false)
    expect(Object.keys(userCreateSchema.shape)).not.toContain('role')
  })
})

describe('User Management page', () => {
  it('lets an Owner create a Branch User, sending no role', async () => {
    const calls = api(PROFILE_OWNER)
    const user = userEvent.setup()
    renderApp('/users')
    await user.click(await screen.findByRole('button', { name: /New Branch User/ }))
    await user.type(screen.getByLabelText(/Full name/), 'New Person')
    await user.type(screen.getByLabelText(/Email/), 'new@example.com')
    await user.click(screen.getByRole('combobox', { name: /Branch/ }))
    await user.click(await screen.findByRole('option', { name: 'Test Branch One' }))
    await user.type(screen.getByLabelText(/^Password/), PW)
    await user.type(screen.getByLabelText(/Confirm password/), PW)
    await user.click(screen.getByRole('button', { name: 'Create user' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'post')).toBe(true))
    const post = calls.find((c) => c.method === 'post')!
    expect(JSON.parse(post.data as string)).toEqual({
      email: 'new@example.com',
      full_name: 'New Person',
      branch_id: 'b1',
      password: PW,
      confirm_password: PW,
    })
    // The password must not be persisted anywhere in the browser.
    expect(JSON.stringify({ ...localStorage })).not.toContain(PW)
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(PW)
  })

  it('does not submit when the passwords differ', async () => {
    const calls = api(PROFILE_OWNER)
    const user = userEvent.setup()
    renderApp('/users')
    await user.click(await screen.findByRole('button', { name: /New Branch User/ }))
    await user.type(screen.getByLabelText(/Full name/), 'New Person')
    await user.type(screen.getByLabelText(/Email/), 'new@example.com')
    await user.click(screen.getByRole('combobox', { name: /Branch/ }))
    await user.click(await screen.findByRole('option', { name: 'Test Branch One' }))
    await user.type(screen.getByLabelText(/^Password/), PW)
    await user.type(screen.getByLabelText(/Confirm password/), PW + 'x')
    await user.click(screen.getByRole('button', { name: 'Create user' }))
    expect(await screen.findByText('Passwords do not match')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'post')).toBe(false)
  })

  it('shows the server error (e.g. duplicate email) inside the dialog', async () => {
    api(PROFILE_OWNER, () =>
      apiError(409, 'conflict', 'An account with this email already exists.'),
    )
    const user = userEvent.setup()
    renderApp('/users')
    await user.click(await screen.findByRole('button', { name: /New Branch User/ }))
    await user.type(screen.getByLabelText(/Full name/), 'New Person')
    await user.type(screen.getByLabelText(/Email/), 'new@example.com')
    await user.click(screen.getByRole('combobox', { name: /Branch/ }))
    await user.click(await screen.findByRole('option', { name: 'Test Branch One' }))
    await user.type(screen.getByLabelText(/^Password/), PW)
    await user.type(screen.getByLabelText(/Confirm password/), PW)
    await user.click(screen.getByRole('button', { name: 'Create user' }))
    expect(
      await screen.findByText('An account with this email already exists.'),
    ).toBeInTheDocument()
  })

  it('blocks a Branch User from the page entirely', async () => {
    api(PROFILE_BRANCH)
    renderApp('/users')
    expect(await screen.findByText('Access denied')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /New Branch User/ })).not.toBeInTheDocument()
  })
})
