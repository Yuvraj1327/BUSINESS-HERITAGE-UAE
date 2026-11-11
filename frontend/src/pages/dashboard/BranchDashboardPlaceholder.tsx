import { Building2, FileClock, FilePlus2 } from 'lucide-react'
import { Can } from '@/auth/permission-guards'
import { EmptyState } from '@/components/common/empty-state'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Badge } from '@/components/ui/badge'
import { dubaiToday, formatDate } from '@/utils/format'

/** Branch dashboard layout only (real content: Step 7). Shows the assigned branch and today's reporting date. */
export function BranchDashboardPlaceholder() {
  const { selectedBranchName } = useBranchContext()
  return (
    <PageContainer
      title="Dashboard"
      description="Your branch overview. Live figures arrive with the dashboard module."
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border bg-card px-4 py-3 shadow-card">
        <div className="flex items-center gap-2">
          <Building2 className="size-5 text-teal" aria-hidden />
          <h2 className="text-lg font-semibold text-primary">
            {selectedBranchName ?? 'Your branch'}
          </h2>
          <Badge variant="secondary">Assigned branch</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Reporting date:{' '}
          <span className="font-medium text-foreground">{formatDate(dubaiToday())}</span>
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((n) => (
          <StatCard key={n} label={`Key figure ${n}`} placeholder description="Not available yet" />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard title="Recent reporting" className="lg:col-span-2">
          <EmptyState
            icon={FileClock}
            title="No reports to show yet"
            description="Your branch's recent daily reports will be listed here."
            className="border-0 py-8"
          />
        </SectionCard>
        <SectionCard title="Branch actions">
          <Can module="daily_reports" action="create">
            <EmptyState
              icon={FilePlus2}
              title="Daily report entry"
              description="Entering the daily report becomes available with the reporting module."
              className="border-0 py-8"
            />
          </Can>
        </SectionCard>
      </div>
    </PageContainer>
  )
}
