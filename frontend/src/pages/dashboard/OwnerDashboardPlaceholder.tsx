import { BarChart3, ClipboardCheck, LineChart, Table2 } from 'lucide-react'
import { EmptyState } from '@/components/common/empty-state'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { ALL_BRANCHES, useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { FormDatePicker } from '@/components/forms/form-date-picker'

/**
 * Owner dashboard layout only. Every figure, chart and table is an honest placeholder: the real dashboard is built
 * in Step 7, and nothing here is computed or invented.
 */
export function OwnerDashboardPlaceholder() {
  const { selectedBranchId, selectedBranchName } = useBranchContext()
  const branchText =
    selectedBranchId === ALL_BRANCHES ? 'All branches' : (selectedBranchName ?? '—')
  return (
    <PageContainer
      title="Dashboard"
      description="Overview of all branches. Live figures arrive with the dashboard module."
    >
      <SectionCard
        title="Filters"
        description="Placeholders: filtering starts working with the dashboard module."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FormDatePicker label="Date" disabled description="Date filter (not active yet)" />
          <div className="grid gap-1.5">
            <p className="text-sm leading-none font-medium">Branch</p>
            <p className="flex h-9 items-center rounded-md border bg-muted px-3 text-sm">
              {branchText}
            </p>
            <p className="text-xs text-muted-foreground">
              Chosen with the branch selector in the header
            </p>
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((n) => (
          <StatCard key={n} label={`Key figure ${n}`} placeholder description="Not available yet" />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Chart area">
          <EmptyState
            icon={BarChart3}
            title="Chart placeholder"
            description="No data is shown until the dashboard module is built."
            className="border-0 py-8"
          />
        </SectionCard>
        <SectionCard title="Chart area">
          <EmptyState
            icon={LineChart}
            title="Chart placeholder"
            description="No data is shown until the dashboard module is built."
            className="border-0 py-8"
          />
        </SectionCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard title="Table area" className="lg:col-span-2">
          <EmptyState
            icon={Table2}
            title="Table placeholder"
            description="Branch-level records will be listed here."
            className="border-0 py-8"
          />
        </SectionCard>
        <SectionCard title="Needs attention">
          <EmptyState
            icon={ClipboardCheck}
            title="Nothing to show yet"
            description="Items that need the owner's attention will be listed here."
            className="border-0 py-8"
          />
        </SectionCard>
      </div>
    </PageContainer>
  )
}
