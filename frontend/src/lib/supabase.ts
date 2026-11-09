import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { env } from '@/config/env'
import { authStorage } from '@/lib/auth-storage'

/**
 * The single browser Supabase client. It is built ONLY from the public URL and anon (publishable) key; the
 * service-role key must never exist in frontend code (config/env.ts also refuses it). All data access goes
 * through the FastAPI backend, so this client is used for authentication only.
 *
 * PKCE flow: the password-reset link carries a one-time code that is exchanged in the same browser that
 * requested it.
 */
export const supabase: SupabaseClient | null = env.supabaseConfigured
  ? createClient(env.supabaseUrl, env.supabaseAnonKey, {
      auth: {
        flowType: 'pkce',
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        storage: authStorage,
        storageKey: 'alsafa-auth',
      },
    })
  : null
