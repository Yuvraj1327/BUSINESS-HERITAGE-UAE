import type { Session, User } from '@supabase/supabase-js'
import { createContext } from 'react'
import type { UserProfile } from '@/schemas/auth'

/**
 * loading         - restoring the stored session (nothing must flash on screen yet)
 * unauthenticated - no session
 * authenticated   - valid session (the profile is tracked separately)
 * recovery        - arrived through a password-reset link; must set a new password before using the app
 * unconfigured    - Supabase env vars are missing
 */
export type AuthStatus =
  'loading' | 'unauthenticated' | 'authenticated' | 'recovery' | 'unconfigured'

export type ProfileStatus = 'idle' | 'loading' | 'ready' | 'missing' | 'inactive' | 'error'

export interface AuthContextValue {
  status: AuthStatus
  session: Session | null
  user: User | null
  profileStatus: ProfileStatus
  profile: UserProfile | null
  profileError: string | null
  /** Set when a session ended without the user asking (expiry / revoked / signed out elsewhere). */
  sessionEnded: boolean
  clearSessionEnded: () => void
  signOut: () => Promise<void>
  reloadProfile: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
