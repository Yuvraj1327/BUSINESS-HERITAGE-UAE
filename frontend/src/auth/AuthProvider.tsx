import type { Session } from '@supabase/supabase-js'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
  type ProfileStatus,
} from '@/auth/auth-context'
import { toast } from 'sonner'
import {
  setAccessTokenProvider,
  setForbiddenHandler,
  setUnauthorizedHandler,
} from '@/lib/api-client'
import { authStorage } from '@/lib/auth-storage'
import { toApiError } from '@/lib/errors'
import { supabase } from '@/lib/supabase'
import type { UserProfile } from '@/schemas/auth'
import { fetchProfile, getAccessToken, signOutLocal } from '@/services/auth.service'

interface ProfileResult {
  userId: string
  status: Exclude<ProfileStatus, 'idle' | 'loading'>
  profile: UserProfile | null
  error: string | null
}

/**
 * Single source of truth for "who is signed in".
 * - Restores the stored session once (status `loading` until done, so guards never flash the login page).
 * - Follows Supabase's auth-state events: sign-in, sign-out, token refresh, password recovery.
 * - Loads the backend profile for the verified user; a missing or inactive profile never reaches the app.
 * - Feeds the API client its bearer token and reacts to a 401 by ending the local session.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<Session | null>(null)
  const [initialized, setInitialized] = useState(!supabase)
  const [recovery, setRecovery] = useState(false)
  const [sessionEnded, setSessionEnded] = useState(false)
  const [profileResult, setProfileResult] = useState<ProfileResult | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const userInitiatedSignOut = useRef(false)

  useEffect(() => {
    if (!supabase) return
    let active = true
    const { data } = supabase.auth.onAuthStateChange((event, next) => {
      if (!active) return
      setSession(next)
      if (event === 'INITIAL_SESSION') setInitialized(true)
      if (event === 'SIGNED_IN') setSessionEnded(false) // the "session ended" notice only lasts until the next sign-in
      if (event === 'PASSWORD_RECOVERY') setRecovery(true)
      // Hourly token refresh doubles as a permission refresh: a role/branch/active change made by the Owner
      // is picked up without a visible loading state (the old result stays on screen until the new one arrives).
      if (event === 'TOKEN_REFRESHED') setReloadKey((k) => k + 1)
      if (event === 'SIGNED_OUT') {
        setRecovery(false)
        if (!userInitiatedSignOut.current) setSessionEnded(true)
        userInitiatedSignOut.current = false
      }
    })
    // Safety net: never stay on the loading screen if INITIAL_SESSION is not delivered.
    supabase.auth
      .getSession()
      .then(({ data: s }) => {
        if (!active) return
        setSession((prev) => prev ?? s.session)
        setInitialized(true)
      })
      .catch(() => active && setInitialized(true))
    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  const signOut = useCallback(async () => {
    userInitiatedSignOut.current = true
    try {
      await signOutLocal()
    } catch {
      authStorage.removeItem('alsafa-auth') // make sure nothing stays behind even if the call failed
    }
    setSession(null)
    setRecovery(false)
    setProfileResult(null)
    queryClient.clear() // no cached business data may survive a sign-out
  }, [queryClient])

  useEffect(() => {
    setAccessTokenProvider(getAccessToken)
    setUnauthorizedHandler(() => {
      // The backend rejected our token (expired / revoked): end the session here and say so on the login page.
      setSessionEnded(true)
      void signOut()
    })
    let lastRefresh = 0
    setForbiddenHandler((err) => {
      // The server refused something the UI offered: tell the user, and re-read the profile/permissions
      // (throttled) in case their role, branch or active status just changed.
      toast.error('You do not have permission to do that.')
      if (Date.now() - lastRefresh > 5000) {
        lastRefresh = Date.now()
        if (
          [
            'permission_denied',
            'branch_access_denied',
            'account_inactive',
            'profile_missing',
            'password_change_required',
          ].includes(err.code)
        ) {
          setReloadKey((k) => k + 1)
        }
      }
    })
    return () => {
      setAccessTokenProvider(null)
      setUnauthorizedHandler(null)
      setForbiddenHandler(null)
    }
  }, [signOut])

  const status: AuthStatus = !supabase
    ? 'unconfigured'
    : !initialized
      ? 'loading'
      : session
        ? recovery
          ? 'recovery'
          : 'authenticated'
        : 'unauthenticated'

  const userId = session?.user.id ?? null
  const wantsProfile = status === 'authenticated' && userId !== null

  useEffect(() => {
    if (!wantsProfile || !userId) return
    let cancelled = false
    fetchProfile()
      .then((profile) => {
        if (!cancelled) setProfileResult({ userId, status: 'ready', profile, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const apiError = toApiError(err)
        if (apiError.isUnauthorized) return // handled by the unauthorized handler
        const kind =
          apiError.code === 'profile_missing'
            ? 'missing'
            : apiError.code === 'account_inactive'
              ? 'inactive'
              : 'error'
        setProfileResult({ userId, status: kind, profile: null, error: apiError.message })
      })
    return () => {
      cancelled = true
    }
  }, [wantsProfile, userId, reloadKey])

  const current = wantsProfile && profileResult?.userId === userId ? profileResult : null
  const profileStatus: ProfileStatus = !wantsProfile ? 'idle' : (current?.status ?? 'loading')

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      user: session?.user ?? null,
      profileStatus,
      profile: current?.profile ?? null,
      profileError: current?.error ?? null,
      sessionEnded,
      clearSessionEnded: () => setSessionEnded(false),
      signOut,
      applyProfile: (profile: UserProfile) =>
        setProfileResult((prev) =>
          prev && prev.userId === profile.user_id ? { ...prev, status: 'ready', profile } : prev,
        ),
      reloadProfile: () => {
        setProfileResult(null)
        setReloadKey((k) => k + 1)
      },
    }),
    [status, session, profileStatus, current, sessionEnded, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
