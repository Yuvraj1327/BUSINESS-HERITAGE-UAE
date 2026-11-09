import axios from 'axios'
import { env } from '@/config/env'
import { toApiError, type ApiError } from '@/lib/errors'

type TokenProvider = () => string | null | Promise<string | null>

let tokenProvider: TokenProvider | null = null
let unauthorizedHandler: (() => void) | null = null
let forbiddenHandler: ((error: ApiError) => void) | null = null

/** Step 4 registers the Supabase session here; nothing authenticates yet. */
export function setAccessTokenProvider(provider: TokenProvider | null) {
  tokenProvider = provider
}
export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler
}

/** Called for 403s on any request except the profile load itself (which AuthProvider handles directly). */
export function setForbiddenHandler(handler: ((error: ApiError) => void) | null) {
  forbiddenHandler = handler
}

export const apiClient = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 15_000,
  headers: { Accept: 'application/json' },
})

apiClient.interceptors.request.use(async (config) => {
  config.headers.set('X-Request-ID', crypto.randomUUID())
  const token = tokenProvider ? await tokenProvider() : null
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const apiError = toApiError(error)
    if (apiError.isUnauthorized) unauthorizedHandler?.()
    else if (apiError.isForbidden && !isProfileRequest(error)) forbiddenHandler?.(apiError)
    return Promise.reject(apiError)
  },
)

function isProfileRequest(error: unknown): boolean {
  const url = (error as { config?: { url?: string } } | null)?.config?.url
  return url === '/auth/profile'
}
