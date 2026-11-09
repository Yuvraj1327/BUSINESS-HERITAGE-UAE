import { useMemo } from 'react'
import { useAuth } from '@/auth/use-auth'
import { hasPermission, scopeOf, type AppAction, type AppModule } from '@/auth/permissions'

/**
 * Role/permission view of the signed-in user. Permissions arrive together with the profile, and guards only
 * render pages once the profile is ready, so there is no "permissions loading" flicker inside the app.
 * These checks drive what is SHOWN; the backend and RLS decide what is ALLOWED.
 */
export function usePermissions() {
  const { profile, profileStatus } = useAuth()
  return useMemo(
    () => ({
      ready: profileStatus === 'ready' && profile !== null,
      role: profile?.role ?? null,
      isOwner: profile?.role === 'owner',
      branchId: profile?.branch_id ?? null,
      branchName: profile?.branch_name ?? null,
      can: (module: AppModule, action: AppAction = 'read') =>
        hasPermission(profile?.permissions, module, action),
      scope: (module: AppModule) => scopeOf(profile?.permissions, module),
    }),
    [profile, profileStatus],
  )
}
