import type { ReactNode } from 'react'
import { BranchProvider } from '@/components/layout/branch-provider'
import { BranchSelector } from '@/components/layout/branch-selector'
import { AppLayout } from '@/layouts/AppLayout'

/** Layout for users with all-branch scope: global branch selector in the header. */
export function OwnerLayout({ children }: { children?: ReactNode }) {
  return (
    <BranchProvider>
      <AppLayout headerExtra={<BranchSelector />}>{children}</AppLayout>
    </BranchProvider>
  )
}
