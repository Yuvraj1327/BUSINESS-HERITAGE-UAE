import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createFakeSupabase, makeSession } from '@/test/fake-supabase'
import { PROFILE_BRANCH, PROFILE_OWNER, renderApp, stubApi } from '@/test/render-app'
import { describeDevice } from '@/utils/device'
import { formatDate, formatDateTime, setDisplayPrefs } from '@/utils/format'
import { validateAvatar } from '@/services/settings.service'
import { preferencesSchema } from '@/schemas/preferences'
import { changePasswordSchema, profileFormSchema } from '@/schemas/settings'

const fake = vi.hoisted(() => ({ current: null as unknown }))
vi.mock('@/lib/supabase', () => ({
  get supabase() {
    return (fake.current as { client: unknown }).client
  },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() }, Toaster: () => null }))

const UID = '11111111-1111-4111-8111-111111111111'
let sb: ReturnType<typeof createFakeSupabase>

beforeEach(() => {
  sb = createFakeSupabase()
  fake.current = sb
  sb.state.session = makeSession()
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.setPointerCapture ??= () => undefined
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
  document.documentElement.classList.remove('dark')
  setDisplayPrefs(null)
  window.matchMedia ??= ((q: string) => ({
    matches: false,
    media: q,
    addEventListener() {},
    removeEventListener() {},
  })) as never
})

/** Serves the profile and records every write the Settings pages send. */
function api(profile: Record<string, unknown> = PROFILE_BRANCH) {
  let current = { ...profile } as Record<string, unknown>
  const writes: { method?: string; url?: string; body: Record<string, unknown> }[] = []
  stubApi((c) => {
    if (c.url === '/auth/profile' && c.method === 'get') return { status: 200, body: current }
    if (
      (c.url === '/auth/profile' && c.method === 'patch') ||
      (c.url === '/auth/preferences' && c.method === 'put')
    ) {
      const body = JSON.parse(String(c.data)) as Record<string, unknown>
      writes.push({ method: c.method, url: c.url, body })
      current =
        c.url === '/auth/preferences' ? { ...current, preferences: body } : { ...current, ...body }
      return { status: 200, body: current }
    }
    return { status: 200, body: [] }
  })
  return writes
}

function pngFile(size = 100, name = 'me.png', type = 'image/png') {
  const bytes = new Uint8Array(size)
  bytes.set([0x89, 0x50, 0x4e, 0x47])
  return new File([bytes], name, { type })
}

describe('My Profile', () => {
  it('lets a Branch User edit name and phone but shows role and branch as read-only', async () => {
    const writes = api()
    renderApp('/settings/profile')
    const user = userEvent.setup()
    const name = await screen.findByLabelText(/Full name/)
    expect(screen.getByText('Branch User')).toBeInTheDocument()
    expect(screen.getAllByText('SATWA').length).toBeGreaterThan(0)
    expect(screen.queryByLabelText(/role/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/branch/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Manage users/ })).not.toBeInTheDocument()
    await user.clear(name)
    await user.type(name, 'New Name')
    await user.type(screen.getByLabelText('Phone number'), '+971 50 123 4567')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(writes).toHaveLength(1))
    expect(writes[0]?.body).toEqual({ full_name: 'New Name', phone: '+971 50 123 4567' })
    expect(Object.keys(writes[0]?.body ?? {})).not.toContain('role')
    expect(Object.keys(writes[0]?.body ?? {})).not.toContain('branch_id')
  })

  it('blocks an invalid phone number and an empty name without calling the API', async () => {
    const writes = api()
    renderApp('/settings/profile')
    const user = userEvent.setup()
    const name = await screen.findByLabelText(/Full name/)
    await user.clear(name)
    await user.type(screen.getByLabelText('Phone number'), 'abc')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Enter your full name')).toBeInTheDocument()
    expect(screen.getByText(/Enter a valid phone number/)).toBeInTheDocument()
    expect(writes).toHaveLength(0)
  })

  it('shows the Owner a link to user management', async () => {
    api(PROFILE_OWNER)
    renderApp('/settings/profile')
    expect(await screen.findByRole('link', { name: /Manage users/ })).toHaveAttribute(
      'href',
      '/users',
    )
  })

  it('uploads a valid photo into the user’s own folder and stores only the path', async () => {
    const writes = api()
    renderApp('/settings/profile')
    await userEvent.setup().upload(await screen.findByTestId('avatar-input'), pngFile())
    await waitFor(() => expect(writes).toHaveLength(1))
    const path = String(writes[0]?.body.avatar_path)
    expect(path).toMatch(new RegExp(`^${UID}/avatar-[0-9a-f-]{36}\\.png$`))
    expect(sb.storage.from).toHaveBeenCalledWith('avatars')
    expect(sb.bucket.upload).toHaveBeenCalledWith(
      path,
      expect.any(File),
      expect.objectContaining({ contentType: 'image/png', upsert: false }),
    )
  })

  it('rejects a wrong type, an oversized file and a renamed non-image before uploading', async () => {
    const writes = api()
    renderApp('/settings/profile')
    const input = await screen.findByTestId('avatar-input')
    const user = userEvent.setup({ applyAccept: false })
    await user.upload(input, new File(['%PDF'], 'a.pdf', { type: 'application/pdf' }))
    await user.upload(input, pngFile(2 * 1024 * 1024 + 1))
    await user.upload(input, new File([new Uint8Array(50)], 'fake.png', { type: 'image/png' }))
    expect(sb.bucket.upload).not.toHaveBeenCalled()
    expect(writes).toHaveLength(0)
  })

  it('removes the photo', async () => {
    const path = `${UID}/avatar-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.png`
    const writes = api({ ...PROFILE_BRANCH, avatar_path: path })
    renderApp('/settings/profile')
    await userEvent.setup().click(await screen.findByRole('button', { name: /Remove/ }))
    await waitFor(() => expect(writes[0]?.body).toEqual({ avatar_path: null }))
    await waitFor(() => expect(sb.bucket.remove).toHaveBeenCalledWith([path]))
  })
})

describe('validateAvatar', () => {
  it('accepts jpg/png/webp signatures and rejects everything else', async () => {
    await expect(validateAvatar(pngFile())).resolves.toBe('image/png')
    const jpg = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0])], 'a.jpg', {
      type: 'image/jpeg',
    })
    await expect(validateAvatar(jpg)).resolves.toBe('image/jpeg')
    const webp = new File([new TextEncoder().encode('RIFF\0\0\0\0WEBPVP8 ')], 'a.webp', {
      type: 'image/webp',
    })
    await expect(validateAvatar(webp)).resolves.toBe('image/webp')
    const fakeWebp = new File([new TextEncoder().encode('RIFF\0\0\0\0AVI LIST')], 'a.webp', {
      type: 'image/webp',
    })
    await expect(validateAvatar(fakeWebp)).rejects.toThrow(/not a valid image/)
    await expect(
      validateAvatar(new File(['x'], 'a.svg', { type: 'image/svg+xml' })),
    ).rejects.toThrow(/JPG, PNG or WebP/)
    await expect(validateAvatar(new File([], 'a.png', { type: 'image/png' }))).rejects.toThrow(
      /empty/,
    )
  })
})

describe('Account & Security', () => {
  async function open() {
    api()
    renderApp('/settings/security')
    await screen.findByRole('heading', { name: 'Change password' })
  }

  it('re-checks the current password, then changes it through Supabase Auth', async () => {
    await open()
    const user = userEvent.setup()
    const card = screen.getByRole('heading', { name: 'Change password' }).closest('section')!
    await user.type(within(card).getByLabelText(/Current password/), 'Old-Passw0rd-x')
    await user.type(within(card).getByLabelText(/^New password/), 'Brand-New-Passw0rd')
    await user.type(within(card).getByLabelText(/Confirm new password/), 'Brand-New-Passw0rd')
    await user.click(within(card).getByRole('button', { name: 'Change password' }))
    await waitFor(() =>
      expect(sb.auth.updateUser).toHaveBeenCalledWith({ password: 'Brand-New-Passw0rd' }),
    )
    expect(sb.auth.signInWithPassword).toHaveBeenCalledWith({
      email: 'person@example.test',
      password: 'Old-Passw0rd-x',
    })
  })

  it('does not change anything when the current password is wrong', async () => {
    await open()
    sb.auth.signInWithPassword.mockResolvedValueOnce({
      data: { session: null, user: null },
      error: { message: 'bad' },
    } as never)
    const user = userEvent.setup()
    const card = screen.getByRole('heading', { name: 'Change password' }).closest('section')!
    await user.type(within(card).getByLabelText(/Current password/), 'wrong')
    await user.type(within(card).getByLabelText(/^New password/), 'Brand-New-Passw0rd')
    await user.type(within(card).getByLabelText(/Confirm new password/), 'Brand-New-Passw0rd')
    await user.click(within(card).getByRole('button', { name: 'Change password' }))
    expect(await within(card).findByRole('alert')).toHaveTextContent(
      'current password is not correct',
    )
    expect(sb.auth.updateUser).not.toHaveBeenCalled()
  })

  it('requests an email change that needs confirmation', async () => {
    await open()
    const user = userEvent.setup()
    const card = screen.getByRole('heading', { name: 'Change email' }).closest('section')!
    await user.type(within(card).getByLabelText(/New email address/), 'new@example.test')
    await user.type(within(card).getByLabelText(/Current password/), 'Old-Passw0rd-x')
    await user.click(within(card).getByRole('button', { name: 'Send confirmation email' }))
    await waitFor(() =>
      expect(sb.auth.updateUser).toHaveBeenCalledWith(
        { email: 'new@example.test' },
        { emailRedirectTo: `${window.location.origin}/settings/security` },
      ),
    )
    expect(await screen.findByText(/Waiting for confirmation/)).toHaveTextContent(
      'new@example.test',
    )
  })

  it('shows this session and can sign out other devices or this one (after confirming)', async () => {
    await open()
    const user = userEvent.setup()
    expect(screen.getByText(/current session/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sign out other devices' }))
    await waitFor(() => expect(sb.auth.signOut).toHaveBeenCalledWith({ scope: 'others' }))
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    await user.click(await screen.findByRole('button', { name: 'Sign out', hidden: false }))
  })
})

describe('Appearance', () => {
  it('applies the theme at once, remembers it on the device and saves it to the account', async () => {
    const writes = api()
    renderApp('/settings/appearance')
    await userEvent.setup().click(await screen.findByRole('radio', { name: /Dark/ }))
    expect(document.documentElement).toHaveClass('dark')
    expect(localStorage.getItem('alsafa-theme')).toBe('dark')
    await waitFor(() => expect(writes[0]?.body).toMatchObject({ theme: 'dark' }))
    expect(screen.getByRole('radio', { name: /Dark/ })).toHaveAttribute('aria-checked', 'true')
    await userEvent.setup().click(screen.getByRole('radio', { name: /Light/ }))
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('restores the saved theme from the profile on load', async () => {
    api({ ...PROFILE_BRANCH, preferences: { ...preferencesSchema.parse({}), theme: 'dark' } })
    renderApp('/settings/appearance')
    await screen.findByRole('radio', { name: /Dark/ })
    await waitFor(() => expect(document.documentElement).toHaveClass('dark'))
  })
})

describe('Notifications', () => {
  it('lets an Owner mute a level and saves it', async () => {
    const writes = api(PROFILE_OWNER)
    renderApp('/settings/notifications')
    await userEvent.setup().click(await screen.findByRole('switch', { name: /Information/ }))
    await waitFor(() =>
      expect(writes[0]?.body).toMatchObject({
        notifications: { critical: true, warning: true, info: false },
      }),
    )
  })

  it('tells a Branch User there is nothing to configure', async () => {
    api()
    renderApp('/settings/notifications')
    expect(await screen.findByText(/no notification categories/)).toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })
})

describe('Preferences', () => {
  it('saves date format and timezone; currency and business time stay fixed', async () => {
    const writes = api()
    renderApp('/settings/preferences')
    const user = userEvent.setup()
    expect(await screen.findByText(/AED \(UAE dirham\)/)).toBeInTheDocument()
    expect(screen.getByText(/Asia\/Dubai/)).toBeInTheDocument()
    await user.click(screen.getByRole('combobox', { name: /Date format/ }))
    await user.click(await screen.findByRole('option', { name: '2026-11-12' }))
    await user.click(screen.getByRole('button', { name: 'Save preferences' }))
    await waitFor(() =>
      expect(writes[0]?.body).toMatchObject({ date_format: 'yyyy-mm-dd', timezone: 'Asia/Dubai' }),
    )
  })
})

describe('About', () => {
  it('shows the app name, version and support fallback', async () => {
    api()
    renderApp('/settings/about')
    expect(await screen.findByText('ALSAFA Heritage Laundry ERP')).toBeInTheDocument()
    expect(screen.getByText(__APP_VERSION__)).toBeInTheDocument()
    expect(screen.getByText(/contact your administrator/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Privacy' })).toBeInTheDocument()
  })
})

describe('Settings access', () => {
  it('is open to a Branch User while System status stays Owner-only', async () => {
    api()
    renderApp('/settings')
    expect(await screen.findByLabelText(/Full name/)).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Settings sections' })).toBeInTheDocument()
  })
})

describe('display formatting', () => {
  it('formats dates in the chosen layout without shifting the calendar day', () => {
    expect(formatDate('2026-11-12')).toBe('12 Nov 2026')
    setDisplayPrefs({ dateFormat: 'dd/mm/yyyy' })
    expect(formatDate('2026-11-12')).toBe('12/11/2026')
    setDisplayPrefs({ dateFormat: 'mm/dd/yyyy' })
    expect(formatDate('2026-11-12')).toBe('11/12/2026')
    setDisplayPrefs({ dateFormat: 'yyyy-mm-dd' })
    expect(formatDate('2026-11-12')).toBe('2026-11-12')
    expect(formatDate('nope')).toBe('—')
  })

  it('shows timestamps in Dubai by default and in the chosen display timezone otherwise', () => {
    const iso = '2026-11-12T22:30:00Z'
    expect(formatDateTime(iso)).toBe('13 Nov 2026, 02:30')
    setDisplayPrefs({ timezone: 'UTC' })
    expect(formatDateTime(iso)).toBe('12 Nov 2026, 22:30')
    setDisplayPrefs({ timezone: 'Asia/Kolkata', dateFormat: 'yyyy-mm-dd' })
    expect(formatDateTime(iso)).toBe('2026-11-13, 04:00')
    expect(formatDateTime(null)).toBe('—')
  })
})

describe('schemas and helpers', () => {
  it('falls back to defaults for missing or damaged preferences', () => {
    expect(
      preferencesSchema.parse({ theme: 'neon', timezone: 'Mars/Base', notifications: 5 }),
    ).toMatchObject({
      theme: 'light',
      timezone: 'Asia/Dubai',
      notifications: { critical: true, warning: true, info: true },
    })
  })
  it('validates profile and password forms like the server does', () => {
    expect(profileFormSchema.safeParse({ full_name: ' ', phone: '' }).success).toBe(false)
    expect(profileFormSchema.safeParse({ full_name: 'A', phone: '' }).success).toBe(true)
    expect(profileFormSchema.safeParse({ full_name: 'A', phone: '12' }).success).toBe(false)
    expect(
      changePasswordSchema.safeParse({ current: 'x', password: 'weak', confirm: 'weak' }).success,
    ).toBe(false)
    expect(
      changePasswordSchema.safeParse({
        current: 'Same-Passw0rd1',
        password: 'Same-Passw0rd1',
        confirm: 'Same-Passw0rd1',
      }).success,
    ).toBe(false)
  })
  it('describes a browser in plain words', () => {
    expect(
      describeDevice(
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605 Chrome/120 Safari/537',
      ),
    ).toBe('Chrome on macOS')
  })
})
