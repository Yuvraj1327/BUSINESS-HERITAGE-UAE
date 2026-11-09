import { AuthApiError, isAuthRetryableFetchError, type AuthError } from '@supabase/supabase-js'

export type AuthErrorKind =
  | 'invalid_credentials'
  | 'email_not_confirmed'
  | 'rate_limited'
  | 'network'
  | 'weak_password'
  | 'same_password'
  | 'session_invalid'
  | 'unknown'

export interface FriendlyAuthError {
  kind: AuthErrorKind
  message: string
}

/**
 * One place that turns Supabase auth failures into user-safe text. Wrong-email and wrong-password are
 * deliberately indistinguishable, so the form never reveals whether an account exists.
 */
export function describeAuthError(err: unknown): FriendlyAuthError {
  const e = err as Partial<AuthError> | null | undefined
  const code = typeof e?.code === 'string' ? e.code : ''
  const status = typeof e?.status === 'number' ? e.status : 0

  if (err && isAuthRetryableFetchError(err as AuthError)) return network()
  if (err instanceof TypeError || e?.name === 'AuthRetryableFetchError') return network()
  if (
    code === 'invalid_credentials' ||
    (err instanceof AuthApiError && status === 400 && /invalid login/i.test(e?.message ?? ''))
  ) {
    return { kind: 'invalid_credentials', message: 'Incorrect email or password.' }
  }
  if (code === 'email_not_confirmed') {
    return {
      kind: 'email_not_confirmed',
      message: 'This email address has not been confirmed. Please contact the administrator.',
    }
  }
  if (
    status === 429 ||
    code === 'over_request_rate_limit' ||
    code === 'over_email_send_rate_limit'
  ) {
    return {
      kind: 'rate_limited',
      message: 'Too many attempts. Please wait a few minutes and try again.',
    }
  }
  if (code === 'weak_password') {
    return {
      kind: 'weak_password',
      message: 'That password is too weak. Use at least 10 characters with letters and numbers.',
    }
  }
  if (code === 'same_password') {
    return { kind: 'same_password', message: 'Choose a password different from your current one.' }
  }
  if (
    [
      'session_not_found',
      'session_expired',
      'refresh_token_not_found',
      'refresh_token_already_used',
      'bad_jwt',
    ].includes(code) ||
    status === 401
  ) {
    return {
      kind: 'session_invalid',
      message: 'Your reset link or session has expired. Please request a new link.',
    }
  }
  return { kind: 'unknown', message: 'Something went wrong. Please try again.' }
}

function network(): FriendlyAuthError {
  return {
    kind: 'network',
    message: 'Cannot reach the sign-in service. Check your connection and try again.',
  }
}
