import { Construction } from 'lucide-react'
import { EmptyState } from '@/components/common/empty-state'
import { PageContainer } from '@/components/layout/page-container'
import type { NavItem } from '@/config/navigation'

/** Protected route for a module that is on the menu but not built yet. No data, no actions. */
export function ModulePlaceholderPage({ item }: { item: NavItem }) {
  return (
    <PageContainer title={item.label}>
      <EmptyState
        icon={Construction}
        title="This module is not built yet"
        description={`${item.label} will appear here when it is added to the system.`}
      />
    </PageContainer>
  )
}
