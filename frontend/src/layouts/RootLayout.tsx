import { Fragment, type ReactNode } from 'react'
import { useAuth } from '@/auth/use-auth'
import { useLayoutVariant } from '@/auth/use-navigation'
import { BranchLayout } from '@/layouts/BranchLayout'
import { OwnerLayout } from '@/layouts/OwnerLayout'
import { setDisplayPrefs } from '@/utils/format'

/**
 * Picks the shell for the signed-in user. The choice follows the server-sent dashboard scope (all branches vs
 * own branch), not a role name typed in the frontend. Sits inside <ProtectedRoute>, so the profile is ready.
 *
 * It also hands the user's date/timezone preferences to the formatters before anything renders, and remounts the
 * shell when one of them changes so every date on screen is re-formatted at once.
 */
export function RootLayout({ children }: { children?: ReactNode }) {
  const variant = useLayoutVariant()
  const { profile } = useAuth()
  const dateFormat = profile?.preferences.date_format
  const timezone = profile?.preferences.timezone
  setDisplayPrefs({ dateFormat, timezone }) // idempotent module setting, must precede the render of the pages
  return (
    <Fragment key={`${dateFormat}|${timezone}`}>
      {variant === 'owner' ? (
        <OwnerLayout>{children}</OwnerLayout>
      ) : (
        <BranchLayout>{children}</BranchLayout>
      )}
    </Fragment>
  )
}
