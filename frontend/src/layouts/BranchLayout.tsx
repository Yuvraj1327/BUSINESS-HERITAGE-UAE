import type { ReactNode } from 'react'
import { AssignedBranch } from '@/components/layout/branch-selector'
import { BranchProvider } from '@/components/layout/branch-provider'
import { AppLayout } from '@/layouts/AppLayout'

/** Layout for users limited to one branch: shows the assignment, offers no branch choice. */
export function BranchLayout({ children }: { children?: ReactNode }) {
  return (
    <BranchProvider>
      <AppLayout headerExtra={<AssignedBranch />}>{children}</AppLayout>
    </BranchProvider>
  )
}
