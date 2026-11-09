import { describe, expect, it } from 'vitest'
import { parseEnv } from '@/config/env'
import { describeAuthError } from '@/lib/auth-errors'

const base = {
  MODE: 'production',
  DEV: false,
  PROD: true,
  VITE_API_BASE_URL: 'https://api.example.com/api/v1',
}
const good = {
  ...base,
  VITE_SUPABASE_URL: 'https://abcd.supabase.co',
  VITE_SUPABASE_ANON_KEY: 'public-anon-key',
}

function jwt(role: string) {
  const b = (o: object) => btoa(JSON.stringify(o)).replace(/=/g, '')
  return `${b({ alg: 'HS256' })}.${b({ role })}.sig`
}

describe('env', () => {
  it('requires Supabase settings in production builds', () => {
    expect(() => parseEnv(base)).toThrow(/VITE_SUPABASE_URL/)
    expect(parseEnv(good).supabaseConfigured).toBe(true)
  })
  it('requires https for Supabase in production', () => {
    expect(() => parseEnv({ ...good, VITE_SUPABASE_URL: 'http://abcd.supabase.co' })).toThrow(
      /https/,
    )
  })
  it('refuses any service-role variable or key', () => {
    expect(() => parseEnv({ ...good, VITE_SUPABASE_SERVICE_ROLE_KEY: 'x' })).toThrow(
      /never be exposed/,
    )
    expect(() => parseEnv({ ...good, VITE_SUPABASE_ANON_KEY: jwt('service_role') })).toThrow(
      /service-role/,
    )
  })
  it('allows an unconfigured dev environment', () => {
    expect(parseEnv({ MODE: 'development', DEV: true, PROD: false }).supabaseConfigured).toBe(false)
  })
})

describe('describeAuthError', () => {
  const e = (code: string, status: number, message = 'x') => ({
    name: 'AuthApiError',
    code,
    status,
    message,
  })
  it('maps known failures to safe messages', () => {
    expect(describeAuthError(e('invalid_credentials', 400)).kind).toBe('invalid_credentials')
    expect(describeAuthError(e('over_request_rate_limit', 429)).kind).toBe('rate_limited')
    expect(describeAuthError(e('weak_password', 422)).kind).toBe('weak_password')
    expect(describeAuthError(e('email_not_confirmed', 400)).kind).toBe('email_not_confirmed')
    expect(describeAuthError(e('session_expired', 401)).kind).toBe('session_invalid')
  })
  it('treats fetch failures as network errors and never leaks raw messages', () => {
    expect(describeAuthError(new TypeError('Failed to fetch')).kind).toBe('network')
    const out = describeAuthError(e('something_odd', 500, 'database exploded at host 10.0.0.1'))
    expect(out.kind).toBe('unknown')
    expect(out.message).not.toContain('10.0.0.1')
  })
})
