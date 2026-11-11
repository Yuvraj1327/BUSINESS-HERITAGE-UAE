import type { ReactNode } from 'react'
import { useLayoutVariant } from '@/auth/use-navigation'
import { BranchLayout } from '@/layouts/BranchLayout'
import { OwnerLayout } from '@/layouts/OwnerLayout'

/**
 * Picks the shell for the signed-in user. The choice follows the server-sent dashboard scope (all branches vs
 * own branch), not a role name typed in the frontend. Sits inside <ProtectedRoute>, so the profile is ready.
 */
export function RootLayout({ children }: { children?: ReactNode }) {
  const variant = useLayoutVariant()
  return variant === 'owner' ? (
    <OwnerLayout>{children}</OwnerLayout>
  ) : (
    <BranchLayout>{children}</BranchLayout>
  )
}
