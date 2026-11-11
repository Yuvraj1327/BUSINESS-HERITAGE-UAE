import { Archive, ArrowLeft, Pencil, Plane, UserCheck, UserX } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import {
  useArchiveEmployee,
  useChangeStatus,
  useCorrectLeave,
  useEmployee,
  useReturnToWork,
  useUpdateExpiry,
} from '@/hooks/use-hr'
import { formatAED, formatDate, dubaiToday } from '@/utils/format'
import { EmployeeDialog } from './EmployeeDialog'
import { ActionDialog, ChangeHistory, EmploymentBadge, ExpiryBadge, LeaveBadge } from './shared'

type Action = 'leave' | 'return' | 'cancel' | 'correct' | 'archive' | 'visa' | 'passport' | null

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="col-span-2">{children}</dd>
    </div>
  )
}

export function EmployeeDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const detail = useEmployee(id)
  const status = useChangeStatus()
  const back = useReturnToWork()
  const correct = useCorrectLeave()
  const archive = useArchiveEmployee()
  const expiry = useUpdateExpiry()
  const [editing, setEditing] = useState(false)
  const [action, setAction] = useState<Action>(null)
  const today = dubaiToday()

  if (detail.isLoading) return <LoadingState label="Loading employee…" />
  if (detail.error || !detail.data)
    return (
      <PageContainer title="Employee">
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      </PageContainer>
    )
  const e = detail.data.employee
  const close = (o: boolean) => !o && setAction(null)
  const onLeave = e.stored_status === 'Leave' && !e.visa_cancelled
  const frozen = e.archived

  return (
    <PageContainer
      title={e.full_name}
      description={[e.role_title, e.branch_name].filter(Boolean).join(' · ')}
      actions={
        <>
          <Button variant="outline" asChild>
            <Link to="/employees">
              <ArrowLeft aria-hidden /> All employees
            </Link>
          </Button>
          <Can module="employees" action="update">
            <Button variant="outline" onClick={() => setEditing(true)} disabled={frozen}>
              <Pencil aria-hidden /> Edit
            </Button>
          </Can>
        </>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <EmploymentBadge status={e.status} />
        {e.leave ? <LeaveBadge state={e.leave.state} /> : null}
        {e.archived ? (
          <span className="text-sm text-muted-foreground">Archived: {e.archive_reason}</span>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Monthly salary"
          value={formatAED(e.monthly_salary)}
          description={
            e.payroll_eligible ? 'Counted in monthly payroll' : 'Not counted in monthly payroll'
          }
        />
        <StatCard
          label="Visa"
          value={<ExpiryBadge status={e.visa_status} days={e.visa_days_remaining} />}
          description={e.visa_expiry ? `Expires ${formatDate(e.visa_expiry)}` : undefined}
        />
        <StatCard
          label="Passport"
          value={<ExpiryBadge status={e.passport_status} days={e.passport_days_remaining} />}
          description={e.passport_expiry ? `Expires ${formatDate(e.passport_expiry)}` : undefined}
        />
        <StatCard
          label="Leave"
          value={e.leave ? `${e.leave.days_on_leave} days` : 'Not on leave'}
          description={e.leave ? `Since ${formatDate(e.leave.leave_start)}` : undefined}
        />
      </div>

      <Can module="employees" action="update">
        {!frozen ? (
          <div className="flex flex-wrap gap-2" aria-label="Status actions">
            {!e.visa_cancelled && e.stored_status === 'Active' ? (
              <Button variant="outline" onClick={() => setAction('leave')}>
                <Plane aria-hidden /> Start leave
              </Button>
            ) : null}
            {e.stored_status === 'Leave' ? (
              <Button onClick={() => setAction('return')}>
                <UserCheck aria-hidden /> Return to work
              </Button>
            ) : null}
            {onLeave ? (
              <Button variant="outline" onClick={() => setAction('correct')}>
                Correct leave start
              </Button>
            ) : null}
            {!e.visa_cancelled ? (
              <Button variant="outline" onClick={() => setAction('cancel')}>
                <UserX aria-hidden /> Cancel visa
              </Button>
            ) : null}
            <Button variant="outline" onClick={() => setAction('archive')}>
              <Archive aria-hidden /> Archive
            </Button>
          </div>
        ) : null}
      </Can>

      {e.leave ? (
        <SectionCard
          title="Leave and six-month limit"
          description="The limit is six calendar months from the leave start date, not 180 days. The limit date is the last allowed day."
        >
          <dl>
            <Row label="Leave start">{formatDate(e.leave.leave_start)}</Row>
            <Row label="Current duration">{e.leave.days_on_leave} days</Row>
            <Row label="Six-month limit date">{formatDate(e.leave.limit_date)}</Row>
            <Row label="Days remaining">
              {e.leave.days_remaining >= 0 ? e.leave.days_remaining : 'Limit passed'}
            </Row>
            <Row label="Leave status">
              <LeaveBadge state={e.leave.state} />
            </Row>
          </dl>
          {e.leave.state === 'visa_cancelled' ? (
            <p
              role="status"
              className="mt-3 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm"
            >
              The six-month limit has passed, so the visa is cancelled. Returning to work now
              records the cancellation permanently.
            </p>
          ) : null}
        </SectionCard>
      ) : null}

      <SectionCard
        title="Details"
        actions={
          <Can module="visas_passports" action="update">
            {!frozen ? (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={e.visa_cancelled}
                  onClick={() => setAction('visa')}
                >
                  Update visa expiry
                </Button>
                <Button size="sm" variant="outline" onClick={() => setAction('passport')}>
                  Update passport expiry
                </Button>
              </div>
            ) : null}
          </Can>
        }
      >
        <dl>
          <Row label="Branch">{e.branch_name}</Row>
          <Row label="Job role">{e.role_title ?? '—'}</Row>
          <Row label="Visa expiry">{e.visa_expiry ? formatDate(e.visa_expiry) : '—'}</Row>
          <Row label="Passport expiry">
            {e.passport_expiry ? formatDate(e.passport_expiry) : '—'}
          </Row>
          {e.visa_cancelled ? (
            <Row label="Visa cancelled on">
              {e.visa_cancelled_date ? formatDate(e.visa_cancelled_date) : '—'}
            </Row>
          ) : null}
          <Row label="Notes">{e.notes ?? '—'}</Row>
          <Row label="Created">
            {formatDate(e.created_at.slice(0, 10))} by {e.created_by_name ?? '—'}
          </Row>
          <Row label="Last updated">
            {formatDate(e.updated_at.slice(0, 10))} by {e.updated_by_name ?? '—'}
          </Row>
        </dl>
      </SectionCard>

      <SectionCard title="History" description="Every change, who made it and why.">
        <ChangeHistory entries={detail.data.history} />
      </SectionCard>

      <EmployeeDialog open={editing} onOpenChange={setEditing} employee={e} />

      {action === 'leave' ? (
        <ActionDialog
          open
          onOpenChange={close}
          title="Start leave?"
          description="The employee is shown as On Leave and leaves the monthly payroll total. The visa will be cancelled if they have not returned within six calendar months."
          confirmLabel="Start leave"
          dateLabel="Leave start date"
          dateDefault={today}
          dateMax={today}
          onSubmit={async (v) => {
            await status.mutateAsync({
              id,
              body: { status: 'On Leave', leave_start: v.date, reason: v.reason },
            })
            toast.success('Leave started')
          }}
        />
      ) : null}
      {action === 'return' ? (
        <ActionDialog
          open
          onOpenChange={close}
          title="Return to work?"
          description={
            e.leave?.state === 'visa_cancelled'
              ? 'The six-month limit has passed. Returning now makes the visa cancellation permanent.'
              : 'The employee becomes Active again. Their visa is kept because they return within six calendar months.'
          }
          destructive={e.leave?.state === 'visa_cancelled'}
          confirmLabel="Return to work"
          dateLabel="Return date"
          dateDefault={today}
          dateMax={today}
          {...(e.leave ? { dateMin: e.leave.leave_start } : {})}
          onSubmit={async (v) => {
            await back.mutateAsync({ id, return_date: v.date, reason: v.reason })
            toast.success('Return to work recorded')
          }}
        />
      ) : null}
      {action === 'correct' ? (
        <ActionDialog
          open
          onOpenChange={close}
          title="Correct the leave start date"
          description="Use this only to fix a data-entry mistake. The correction and your reason are kept in the history."
          confirmLabel="Save correction"
          dateLabel="Leave start date"
          dateDefault={e.leave?.leave_start ?? ''}
          dateMax={today}
          onSubmit={async (v) => {
            await correct.mutateAsync({ id, leave_start: v.date, reason: v.reason })
            toast.success('Leave start corrected')
          }}
        />
      ) : null}
      {action === 'cancel' ? (
        <ActionDialog
          open
          onOpenChange={close}
          title="Cancel this visa?"
          description="This is permanent: the visa cannot be reinstated in the system, and the employee leaves the payroll total."
          destructive
          confirmLabel="Cancel visa"
          dateLabel="Cancellation date"
          dateDefault={today}
          dateMax={today}
          onSubmit={async (v) => {
            await status.mutateAsync({
              id,
              body: { status: 'Visa Cancelled', cancellation_date: v.date, reason: v.reason },
            })
            toast.success('Visa cancelled')
          }}
        />
      ) : null}
      {action === 'archive' ? (
        <ActionDialog
          open
          onOpenChange={close}
          title="Archive this employee?"
          description="Employees are never deleted. An archived employee is hidden from lists, payroll and alerts, and the record stays in the history."
          destructive
          confirmLabel="Archive"
          onSubmit={async (v) => {
            await archive.mutateAsync({ id, reason: v.reason })
            toast.success('Employee archived')
            navigate('/employees')
          }}
        />
      ) : null}
      {action === 'visa' || action === 'passport' ? (
        <ActionDialog
          open
          onOpenChange={close}
          title={action === 'visa' ? 'Update visa expiry' : 'Update passport expiry'}
          description="Only the expiry date is stored (no numbers). The old and new dates are kept in the history."
          confirmLabel="Save expiry"
          dateLabel="New expiry date"
          dateDefault={(action === 'visa' ? e.visa_expiry : e.passport_expiry) ?? ''}
          reasonRequired={false}
          reasonLabel="Reason (optional)"
          onSubmit={async (v) => {
            await expiry.mutateAsync({
              id,
              kind: action,
              expiry_date: v.date,
              ...(v.reason ? { reason: v.reason } : {}),
            })
            toast.success('Expiry date updated')
          }}
        />
      ) : null}
    </PageContainer>
  )
}
