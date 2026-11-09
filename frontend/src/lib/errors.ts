import { isAxiosError } from 'axios'
import type { ApiErrorBody } from '@/types/api'

/** Normalised error thrown by every API call so UI code handles one shape. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string[]>
  readonly requestId: string | null

  constructor(init: {
    message: string
    status: number
    code: string
    fields?: Record<string, string[]> | null
    requestId?: string | null
  }) {
    super(init.message)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.fields = init.fields ?? {}
    this.requestId = init.requestId ?? null
  }

  get isUnauthorized() {
    return this.status === 401
  }
  get isForbidden() {
    return this.status === 403
  }
  get isNetwork() {
    return this.status === 0
  }
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err
  if (isAxiosError(err)) {
    const body = err.response?.data as Partial<ApiErrorBody> | undefined
    if (body?.error) {
      return new ApiError({
        message: body.error.message,
        status: err.response?.status ?? 0,
        code: body.error.code,
        fields: body.error.fields,
        requestId: body.request_id,
      })
    }
    if (!err.response) {
      return new ApiError({
        message: 'Cannot reach the server. Check your connection and try again.',
        status: 0,
        code: err.code === 'ECONNABORTED' ? 'timeout' : 'network_error',
      })
    }
    return new ApiError({
      message: `Request failed (${err.response.status}).`,
      status: err.response.status,
      code: 'http_error',
    })
  }
  return new ApiError({
    message: err instanceof Error ? err.message : 'Something went wrong.',
    status: 0,
    code: 'unknown_error',
  })
}

export function getErrorMessage(err: unknown): string {
  return toApiError(err).message
}
