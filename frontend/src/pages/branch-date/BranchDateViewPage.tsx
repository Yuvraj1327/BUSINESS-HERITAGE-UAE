import { CalendarSearch } from 'lucide-react'
import { useState } from 'react'
import { Can } from '@/auth/permission-guards'
import { SectionCard } from '@/components/common/section-card'
import { ErrorState } from '@/components/common/error-state'
import { StatCard } from '@/components/common/stat-card'
import { DataTable } from '@/components/common/data-table'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormSelect } from '@/components/forms/form-select'
import { ALL_BRANCHES, useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { CollectionBreakdown } from '@/components/reporting/collection-breakdown'
import { MissingPanel } from '@/components/reporting/missing-panel'
import { ReportsTable } from '@/components/reporting/reports-table'
import { Button } from '@/components/ui/button'
import { useBranchDateView } from '@/hooks/use-reports'
import { QUICK_RANGES, quickRange } from '@/utils/period'
import { dubaiToday, formatAED, formatDate } from '@/utils/format'

const MAX_DAYS = 92

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000) + 1
}

export function BranchDateViewPage() {
  const { canChoose, selectedBranchId, selectedBranchName, branches } = useBranchContext()
  const today = dubaiToday()
  const initial = quickRange('last7', today)
  const [branch, setBranch] = useState(selectedBranchId)
  const [from, setFrom] = useState(initial.from)
  const [to, setTo] = useState(initial.to)

  let rangeError: string | undefined
  if (!from || !to) rangeError = 'Choose a start and end date'
  else if (from > to) rangeError = 'Start date must not be after end date'
  else if (to > today) rangeError = 'End date cannot be in the future'
  else if (daysBetween(from, to) > MAX_DAYS) rangeError = `Choose at most ${MAX_DAYS} days`

  const effectiveBranch = canChoose ? branch : ALL_BRANCHES
  const view = useBranchDateView(
    {
      date_from: from,
      date_to: to,
      ...(canChoose && effectiveBranch !== ALL_BRANCHES ? { branch_id: effectiveBranch } : {}),
    },
    !rangeError,
  )
  const t = view.data?.totals

  return (
    <PageContainer
      title="Branch & Date View"
      description={
        canChoose
          ? 'Sales, collections and reports for one branch or all branches.'
          : `Your branch: ${selectedBranchName ?? '—'}`
      }
    >
      <SectionCard title="Filters">
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {canChoose ? (
              <FormSelect
                label="Branch"
                value={branch}
                onValueChange={setBranch}
                options={[
                  { value: ALL_BRANCHES, label: 'All branches' },
                  ...branches.map((b) => ({ value: b.id, label: b.name })),
                ]}
              />
            ) : null}
            <FormDatePicker
              label="From"
              value={from}
              max={to || today}
              onChange={(e) => setFrom(e.target.value)}
            />
            <FormDatePicker
              label="To"
              value={to}
              max={today}
              error={rangeError}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Quick date ranges">
            {QUICK_RANGES.map((q) => (
              <Button
                key={q.key}
                variant="outline"
                size="sm"
                onClick={() => {
                  const r = quickRange(q.key, today)
                  setFrom(r.from)
                  setTo(r.to)
                }}
              >
                {q.label}
              </Button>
            ))}
          </div>
        </div>
      </SectionCard>

      {view.error ? (
        <ErrorState error={view.error} onRetry={() => void view.refetch()} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
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
            <StatCard
              label="Savings"
              isLoading={view.isLoading}
              value={t && formatAED(t.shop_savings)}
            />
            <StatCard label="Total Orders" isLoading={view.isLoading} value={t?.total_orders} />
          </div>

          <CollectionBreakdown totals={t} isLoading={view.isLoading} />

          <SectionCard
            title="Daily reports"
            description={
              view.data
                ? `${formatDate(view.data.date_from)} – ${formatDate(view.data.date_to)}`
                : undefined
            }
          >
            <ReportsTable
              caption="Daily reports in the selected range"
              rows={view.data?.reports}
              isLoading={view.isLoading}
              emptyTitle="No reports in this range"
              emptyDescription="No daily reports were submitted for the selected branch and dates."
            />
          </SectionCard>

          <SectionCard title="Missing reports">
            {view.data ? (
              <MissingPanel missing={view.data.missing} showBranch={view.data.branch_id === null} />
            ) : (
              <p className="text-sm text-muted-foreground">Loading…</p>
            )}
          </SectionCard>

          <Can module="expenses" action="read">
            {view.data?.head_office ? (
              <SectionCard
                title="Head Office expenses"
                description="Excludes savings in the headline figure."
              >
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-3">
                    <StatCard
                      label="Head Office (excl. savings)"
                      value={formatAED(view.data.head_office.excl_savings)}
                    />
                    <StatCard
                      label="Head Office total"
                      value={formatAED(view.data.head_office.total)}
                    />
                    <StatCard
                      label="Head Office savings"
                      value={formatAED(view.data.head_office.savings)}
                    />
                  </div>
                  {view.data.head_office_unallocated &&
                  view.data.head_office_unallocated.count > 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Not included above:{' '}
                      {formatAED(view.data.head_office_unallocated.excl_savings)} of head office
                      spending tagged to all branches.
                    </p>
                  ) : null}
                  <DataTable
                    caption="Head office expenses in range"
                    rows={view.data.head_office_rows ?? []}
                    getRowId={(r) => r.id}
                    emptyIcon={CalendarSearch}
                    emptyTitle="No head office expenses"
                    emptyDescription="None recorded for this branch and period."
                    columns={[
                      { key: 'd', header: 'Date', cell: (r) => formatDate(r.expense_date) },
                      { key: 'b', header: 'Branch', cell: (r) => r.branch_name ?? 'All branches' },
                      { key: 'c', header: 'Category', cell: (r) => r.category },
                      {
                        key: 'a',
                        header: 'Amount',
                        align: 'right',
                        cell: (r) => formatAED(r.amount),
                      },
                      {
                        key: 's',
                        header: 'Type',
                        cell: (r) => (r.is_saving ? 'Saving' : 'Expense'),
                      },
                    ]}
                  />
                </div>
              </SectionCard>
            ) : null}
          </Can>
        </>
      )}
    </PageContainer>
  )
}
