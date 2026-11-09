import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import type { AppAction, AppModule } from '@/auth/permissions'
import { usePermissions } from '@/auth/use-permissions'
import { ForbiddenPage } from '@/pages/auth/ForbiddenPage'

/**
 * Route guard: renders its children only if the user holds `action` on `module`; otherwise the Access denied
 * page, so typing a restricted URL by hand shows nothing of the page. Must sit inside <ProtectedRoute>, which has
 * already waited for the profile (so permissions are known and nothing flickers).
 */
export function RequirePermission({
  module,
  action = 'read',
}: {
  module: AppModule
  action?: AppAction
}) {
  const { ready, can } = usePermissions()
  if (!ready || !can(module, action)) return <ForbiddenPage />
  return <Outlet />
}

/** Renders `children` only when permitted (restricted buttons/links are not rendered at all). */
export function Can({
  module,
  action = 'read',
  children,
  fallback = null,
}: {
  module: AppModule
  action?: AppAction
  children: ReactNode
  fallback?: ReactNode
}) {
  const { can } = usePermissions()
  return <>{can(module, action) ? children : fallback}</>
}
