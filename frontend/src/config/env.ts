import { z } from 'zod'

/**
 * Validated, typed access to Vite environment variables.
 * Fails fast with a readable message. Only VITE_* values exist in the browser bundle, so this module
 * also refuses anything that looks like a Supabase service-role credential.
 */
const rawSchema = z.object({
  MODE: z.string(),
  DEV: z.boolean(),
  PROD: z.boolean(),
  VITE_API_BASE_URL: z.url().optional(),
  VITE_SUPABASE_URL: z.union([z.url(), z.literal('')]).optional(),
  VITE_SUPABASE_ANON_KEY: z.string().optional(),
  VITE_SUPPORT_EMAIL: z.string().optional(),
  VITE_SUPPORT_PHONE: z.string().optional(),
})

const DEV_DEFAULT_API = 'http://localhost:8008/api/v1'

function jwtRole(token: string): string | null {
  const part = token.split('.')[1]
  if (!part) return null
  try {
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    const payload = JSON.parse(json) as { role?: unknown }
    return typeof payload.role === 'string' ? payload.role : null
  } catch {
    return null
  }
}

export function parseEnv(source: Record<string, unknown>) {
  for (const key of Object.keys(source)) {
    if (/service[_-]?role/i.test(key)) {
      throw new Error(`Refusing to start: "${key}" must never be exposed to the browser.`)
    }
  }
  const parsed = rawSchema.safeParse(source)
  if (!parsed.success) {
    const issues = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ')
    throw new Error(`Invalid frontend environment: ${issues}`)
  }
  const e = parsed.data
  if (e.PROD && !e.VITE_API_BASE_URL) {
    throw new Error(
      'Invalid frontend environment: VITE_API_BASE_URL is required in production builds.',
    )
  }
  const anonKey = e.VITE_SUPABASE_ANON_KEY ?? ''
  if (e.PROD && (!e.VITE_SUPABASE_URL || !anonKey)) {
    throw new Error(
      'Invalid frontend environment: VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are required in production builds.',
    )
  }
  if (e.PROD && e.VITE_SUPABASE_URL && !e.VITE_SUPABASE_URL.startsWith('https://')) {
    throw new Error('Invalid frontend environment: VITE_SUPABASE_URL must use https in production.')
  }
  if (anonKey && (jwtRole(anonKey) === 'service_role' || anonKey.startsWith('sb_secret_'))) {
    throw new Error(
      'Refusing to start: VITE_SUPABASE_ANON_KEY contains a secret / service-role key.',
    )
  }
  return {
    mode: e.MODE,
    isDev: e.DEV,
    isProd: e.PROD,
    apiBaseUrl: (e.VITE_API_BASE_URL ?? DEV_DEFAULT_API).replace(/\/+$/, ''),
    supabaseUrl: e.VITE_SUPABASE_URL ?? '',
    supabaseAnonKey: anonKey,
    supportEmail: (e.VITE_SUPPORT_EMAIL ?? '').trim(),
    supportPhone: (e.VITE_SUPPORT_PHONE ?? '').trim(),
    supabaseConfigured: Boolean(e.VITE_SUPABASE_URL && anonKey),
  } as const
}

export const env = parseEnv(import.meta.env as unknown as Record<string, unknown>)
