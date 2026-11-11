import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/auth/use-auth'
import { LoadingIndicator } from '@/components/common/loading-indicator'
import { AccessDeniedPage } from '@/pages/auth/AccessDeniedPage'
import { ChangePasswordPage } from '@/pages/auth/ChangePasswordPage'
import { ConfigMissingPage } from '@/pages/auth/ConfigMissingPage'

function FullScreenLoading({ label }: { label: string }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-background">
      <LoadingIndicator label={label} />
    </div>
  )
}

/**
 * Wraps every page that needs a signed-in, active user.
 * Nothing (not even the login page) renders until the stored session has been restored, so a signed-in user
 * never sees a login flicker. Role-based routing is intentionally NOT here (Step 5/6).
 */
export function ProtectedRoute() {
  const auth = useAuth()
  const location = useLocation()

  switch (auth.status) {
    case 'unconfigured':
      return <ConfigMissingPage />
    case 'loading':
      return <FullScreenLoading label="Restoring your session…" />
    case 'unauthenticated':
      return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
    case 'recovery':
      return <Navigate to="/reset-password" replace />
    case 'authenticated':
      break
  }

  switch (auth.profileStatus) {
    case 'ready':
      // Owner-issued initial password: nothing else is reachable (the API refuses it too) until it is replaced.
      return auth.profile?.must_change_password ? <ChangePasswordPage /> : <Outlet />
    case 'missing':
    case 'inactive':
    case 'error':
      return <AccessDeniedPage />
    default:
      return <FullScreenLoading label="Loading your account…" />
  }
}

/** Login / forgot-password: signed-in users are sent into the app instead. */
export function GuestRoute() {
  const auth = useAuth()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from

  switch (auth.status) {
    case 'unconfigured':
      return <ConfigMissingPage />
    case 'loading':
      return <FullScreenLoading label="Loading…" />
    case 'authenticated':
      return <Navigate to={from && from.startsWith('/') ? from : '/'} replace />
    case 'recovery':
      return <Navigate to="/reset-password" replace />
    default:
      return <Outlet />
  }
}
