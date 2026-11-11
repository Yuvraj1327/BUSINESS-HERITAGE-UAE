import { Ban, ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { SectionCard } from '@/components/common/section-card'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { ALL_BRANCHES, useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { ReportsTable } from '@/components/reporting/reports-table'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useDailyReports, useVoidDailyReport } from '@/hooks/use-reports'
import { toApiError } from '@/lib/errors'
import type { DailyReport } from '@/schemas/reports'
import { dubaiToday } from '@/utils/format'
import { ReportForm, SubmittedSummary } from './ReportForm'

const PAGE_SIZE = 25

export function DailyReportsPage() {
  const { selectedBranchId } = useBranchContext()
  const [submitted, setSubmitted] = useState<DailyReport | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [voiding, setVoiding] = useState<DailyReport | null>(null)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const voidReport = useVoidDailyReport()

  const filters = {
    page,
    page_size: PAGE_SIZE,
    ...(selectedBranchId !== ALL_BRANCHES ? { branch_id: selectedBranchId } : {}),
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  }
  const list = useDailyReports(filters)
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1
  const rangeInvalid = Boolean(dateFrom && dateTo && dateFrom > dateTo)

  async function confirmVoid() {
    if (!voiding) return
    if (reason.trim().length < 3) {
      setReasonError('Enter a reason (at least 3 characters)')
      return
    }
    try {
      await voidReport.mutateAsync({ id: voiding.id, reason: reason.trim() })
      toast.success('Report voided')
      setVoiding(null)
      setReason('')
      setReasonError(null)
    } catch (e) {
      setReasonError(toApiError(e).message)
    }
  }

  return (
    <PageContainer
      title="Daily Reports"
      description="Submit the daily sales report and review report history."
    >
      <Can module="daily_reports" action="create">
        <SectionCard
          title="New daily report"
          description="One report per branch per day. Dates use Dubai time."
        >
          <div className="space-y-4">
            {submitted ? <SubmittedSummary report={submitted} /> : null}
            <ReportForm onSubmitted={setSubmitted} />
          </div>
        </SectionCard>
      </Can>

      <SectionCard
        title="Report history"
        description="Latest reports first. The branch follows the branch selector in the header."
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormDatePicker
              label="From"
              value={dateFrom}
              max={dateTo || dubaiToday()}
              onChange={(e) => {
                setDateFrom(e.target.value)
                setPage(1)
              }}
            />
            <FormDatePicker
              label="To"
              value={dateTo}
              max={dubaiToday()}
              error={rangeInvalid ? 'Start date must not be after end date' : undefined}
              onChange={(e) => {
                setDateTo(e.target.value)
                setPage(1)
              }}
            />
            {dateFrom || dateTo ? (
              <div className="flex items-end">
                <Button
                  variant="outline"
                  onClick={() => {
                    setDateFrom('')
                    setDateTo('')
                    setPage(1)
                  }}
                >
                  Clear dates
                </Button>
              </div>
            ) : null}
          </div>

          <ReportsTable
            caption="Daily report history"
            rows={rangeInvalid ? [] : list.data?.items}
            isLoading={list.isLoading}
            error={list.error}
            onRetry={() => void list.refetch()}
            extra={(r) => (
              <Can module="daily_reports" action="update">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setVoiding(r)}
                  aria-label={`Void report ${r.branch_name} ${r.report_date}`}
                >
                  <Ban aria-hidden /> Void
                </Button>
              </Can>
            )}
          />

          {list.data && list.data.total > 0 ? (
            <nav
              aria-label="Pagination"
              className="flex flex-wrap items-center justify-between gap-2 text-sm"
            >
              <p className="text-muted-foreground" aria-live="polite">
                Page {list.data.page} of {totalPages} · {list.data.total} reports
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft aria-hidden /> Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next <ChevronRight aria-hidden />
                </Button>
              </div>
            </nav>
          ) : null}
        </div>
      </SectionCard>

      <ConfirmDialog
        open={voiding !== null}
        onOpenChange={(open) => {
          if (!open) {
            setVoiding(null)
            setReason('')
            setReasonError(null)
          }
        }}
        title="Void this report?"
        destructive
        confirmLabel="Void report"
        isLoading={voidReport.isPending}
        onConfirm={confirmVoid}
        description={
          voiding ? (
            <div className="space-y-3 text-left text-sm">
              <p>
                {voiding.branch_name} · {voiding.report_date}. The report is removed from all totals
                and the date can be reported again. This is recorded in the audit log.
              </p>
              <label className="grid gap-1.5">
                <span className="font-medium">Reason (required)</span>
                <Textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={500}
                  aria-invalid={reasonError ? true : undefined}
                />
              </label>
              {reasonError ? (
                <p role="alert" className="text-destructive">
                  {reasonError}
                </p>
              ) : null}
            </div>
          ) : null
        }
      />
    </PageContainer>
  )
}
