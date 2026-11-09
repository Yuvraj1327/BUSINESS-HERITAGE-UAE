import type { Session } from '@supabase/supabase-js'
import { vi } from 'vitest'

type Listener = (event: string, session: Session | null) => void

export function makeSession(over: Partial<Session['user']> = {}): Session {
  return {
    access_token: 'access-token-for-tests',
    refresh_token: 'refresh-token-for-tests',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    token_type: 'bearer',
    user: {
      id: '11111111-1111-4111-8111-111111111111',
      email: 'person@example.test',
      aud: 'authenticated',
      app_metadata: {},
      user_metadata: {},
      created_at: '',
      ...over,
    },
  } as Session
}

/** A controllable stand-in for the supabase-js client (no network, no real Supabase). */
export function createFakeSupabase() {
  const listeners = new Set<Listener>()
  const state: { session: Session | null; getSessionGate: Promise<void> | null } = {
    session: null,
    getSessionGate: null,
  }
  const emit = (event: string, session: Session | null) => {
    state.session = session
    listeners.forEach((l) => l(event, session))
  }
  const auth = {
    onAuthStateChange: vi.fn((cb: Listener) => {
      listeners.add(cb)
      // supabase-js delivers INITIAL_SESSION asynchronously after the stored session is restored
      void (state.getSessionGate ?? Promise.resolve()).then(() =>
        cb('INITIAL_SESSION', state.session),
      )
      return { data: { subscription: { unsubscribe: () => listeners.delete(cb) } } }
    }),
    getSession: vi.fn(async () => {
      await state.getSessionGate
      return { data: { session: state.session }, error: null }
    }),
    signInWithPassword: vi.fn(async (_c: { email: string; password: string }) => {
      const s = makeSession()
      emit('SIGNED_IN', s)
      return { data: { session: s, user: s.user }, error: null }
    }),
    signOut: vi.fn(async (_o?: { scope: string }) => {
      emit('SIGNED_OUT', null)
      return { error: null }
    }),
    resetPasswordForEmail: vi.fn(async (_e: string, _o?: { redirectTo: string }) => ({
      data: {},
      error: null as unknown,
    })),
    updateUser: vi.fn(async (_a: { password: string }) => ({ data: {}, error: null as unknown })),
  }
  return { client: { auth }, auth, emit, state }
}
