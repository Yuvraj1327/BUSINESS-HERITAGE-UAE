import type { Session } from '@supabase/supabase-js'
import { apiClient } from '@/lib/api-client'
import { setRememberSession } from '@/lib/auth-storage'
import { supabase } from '@/lib/supabase'
import { profileSchema, type UserProfile } from '@/schemas/auth'

function client() {
  if (!supabase) throw new Error('Supabase is not configured')
  return supabase
}

export async function signInWithPassword(email: string, password: string, remember: boolean) {
  setRememberSession(remember)
  const { data, error } = await client().auth.signInWithPassword({ email, password })
  if (error) throw error
  return data.session
}

/** Ends the session on this device. The short-lived access token already issued stays valid until it expires. */
export async function signOutLocal() {
  const { error } = await client().auth.signOut({ scope: 'local' })
  if (error) throw error
}

export async function requestPasswordReset(email: string) {
  const redirectTo = `${window.location.origin}/reset-password`
  const { error } = await client().auth.resetPasswordForEmail(email, { redirectTo })
  if (error) throw error
}

export async function updatePassword(password: string) {
  const { error } = await client().auth.updateUser({ password })
  if (error) throw error
}

export async function getSession(): Promise<Session | null> {
  const { data, error } = await client().auth.getSession()
  if (error) throw error
  return data.session
}

export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession() // refreshes the token when it is about to expire
  return data.session?.access_token ?? null
}

export async function fetchProfile(): Promise<UserProfile> {
  const { data } = await apiClient.get<unknown>('/auth/profile')
  return profileSchema.parse(data)
}
