import { Building2, FilePlus2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { ErrorState } from '@/components/common/error-state'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageHero } from '@/components/layout/page-hero'
import { MissingPanel } from '@/components/reporting/missing-panel'
import { ReportsTable } from '@/components/reporting/reports-table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useBranchDateView } from '@/hooks/use-reports'
import { addDays } from '@/utils/period'
import { dubaiToday, formatAED, formatDate } from '@/utils/format'

/** A Branch User's dashboard: their own branch only, from the same API as Branch & Date View. */
export function BranchDashboard() {
  const { selectedBranchName } = useBranchContext()
  const today = dubaiToday()
  const view = useBranchDateView({ date_from: addDays(today, -6), date_to: today })
  const t = view.data?.totals

  return (
    <section className="mx-auto w-full max-w-7xl min-w-0 space-y-6 px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
      <PageHero banner title="Dashboard" description="Your branch, last 7 days." />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border bg-card px-4 py-3 shadow-card">
        <div className="flex items-center gap-2">
          <Building2 className="size-5 text-teal" aria-hidden />
          <h2 className="text-lg font-semibold text-primary">
            {selectedBranchName ?? 'Your branch'}
          </h2>
          <Badge variant="secondary">Assigned branch</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Reporting date: <span className="font-medium text-foreground">{formatDate(today)}</span>
        </p>
        <Can module="daily_reports" action="create">
          <Button asChild size="sm" className="ml-auto">
            <Link to="/daily-reports">
              <FilePlus2 aria-hidden /> Submit daily report
            </Link>
          </Button>
        </Can>
      </div>

      {view.error ? (
        <ErrorState error={view.error} onRetry={() => void view.refetch()} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatCard
              label="Total Sales"
              isLoading={view.isLoading}
              value={t && formatAED(t.total_sales)}
            />
            <StatCard
              label="Total Collections"
              isLoading={view.isLoading}
              value={t && formatAED(t.collections.total_received)}
            />
            <StatCard
              label="Shop Expenses (excl. savings)"
              isLoading={view.isLoading}
              value={t && formatAED(t.shop_expenses_excl_savings)}
            />
            <StatCard label="Total Orders" isLoading={view.isLoading} value={t?.total_orders} />
          </div>
          <SectionCard title="Missing reports">
            {view.data ? <MissingPanel missing={view.data.missing} showBranch={false} /> : null}
          </SectionCard>
          <SectionCard
            title="Recent reports"
            actions={
              <Button asChild variant="link" size="sm">
                <Link to="/daily-reports">All reports</Link>
              </Button>
            }
          >
            <ReportsTable
              caption="Recent daily reports"
              rows={view.data?.reports.slice(0, 5)}
              isLoading={view.isLoading}
              emptyTitle="No reports yet"
              emptyDescription="Your branch has no reports in the last 7 days."
            />
          </SectionCard>
        </>
      )}
    </section>
  )
}
