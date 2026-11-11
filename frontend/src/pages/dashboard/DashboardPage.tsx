import { useLayoutVariant } from '@/auth/use-navigation'
import { BranchDashboard } from '@/pages/dashboard/BranchDashboard'
import { OwnerDashboard } from '@/pages/dashboard/OwnerDashboard'

export function DashboardPage() {
  return useLayoutVariant() === 'owner' ? <OwnerDashboard /> : <BranchDashboard />
}
