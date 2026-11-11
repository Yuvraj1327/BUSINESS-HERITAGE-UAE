import { ArrowLeft, CheckCircle2, Pencil } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { ErrorState } from '@/components/common/error-state'
import { LoadingState } from '@/components/common/loading-state'
import { SectionCard } from '@/components/common/section-card'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useSetTaskStatus, useTask } from '@/hooks/use-tasks'
import { toApiError } from '@/lib/errors'
import { TASK_STATUSES, type TaskStatus } from '@/schemas/tasks'
import { formatDate } from '@/utils/format'
import { TaskDialog } from './TaskDialog'
import { dueLabel } from './helpers'
import { TaskHistory, TaskStatusBadge, TimingBadge } from './shared'

const stamp = (iso: string) =>
  new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Dubai',
  }).format(new Date(iso))

export function TaskDetailPage() {
  const { id = '' } = useParams()
  const detail = useTask(id)
  const setStatus = useSetTaskStatus()
  const [editing, setEditing] = useState(false)
  if (detail.isLoading) return <LoadingState label="Loading task…" />
  if (detail.error || !detail.data)
    return (
      <PageContainer title="Task">
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      </PageContainer>
    )
  const t = detail.data.task
  async function change(status: TaskStatus) {
    try {
      await setStatus.mutateAsync({ id, status })
      toast.success(status === 'Done' ? 'Task marked completed' : `Status changed to ${status}`)
    } catch (e) {
      toast.error(toApiError(e).message)
    }
  }
  const rows: [string, React.ReactNode][] = [
    ['Branch', t.branch_name],
    ['Assigned to', t.assignee_name],
    ['Due date', dueLabel(t.due_date)],
    ['Created', `${stamp(t.created_at)} by ${t.created_by_name ?? 'System'}`],
    [
      'Completion date',
      t.completed_at
        ? `${formatDate(t.completed_at.slice(0, 10))} by ${t.completed_by_name ?? '—'}`
        : '—',
    ],
    ['Last updated', `${stamp(t.updated_at)} by ${t.updated_by_name ?? 'System'}`],
  ]
  return (
    <PageContainer
      title={t.title}
      description={t.branch_name}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link to="/tasks">
              <ArrowLeft aria-hidden /> All tasks
            </Link>
          </Button>
          <Can module="tasks" action="update">
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil aria-hidden /> Edit
            </Button>
            {t.status !== 'Done' ? (
              <Button onClick={() => void change('Done')} disabled={setStatus.isPending}>
                <CheckCircle2 aria-hidden /> Mark completed
              </Button>
            ) : null}
          </Can>
        </div>
      }
    >
      <SectionCard title="Details">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <TaskStatusBadge status={t.status} />
          <TimingBadge task={t} />
        </div>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="font-medium">{v}</dd>
            </div>
          ))}
        </dl>
        {t.description ? <p className="mt-4 text-sm whitespace-pre-wrap">{t.description}</p> : null}
        {t.notes ? (
          <p className="mt-3 text-sm whitespace-pre-wrap text-muted-foreground">Notes: {t.notes}</p>
        ) : null}
        <Can module="tasks" action="update">
          <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Change status">
            {TASK_STATUSES.map((s) => (
              <Button
                key={s}
                size="sm"
                variant={t.status === s ? 'default' : 'outline'}
                aria-pressed={t.status === s}
                disabled={t.status === s || setStatus.isPending}
                onClick={() => void change(s)}
              >
                {s}
              </Button>
            ))}
          </div>
        </Can>
      </SectionCard>
      <SectionCard title="History">
        <TaskHistory entries={detail.data.history} />
      </SectionCard>
      <TaskDialog open={editing} onOpenChange={setEditing} task={t} />
    </PageContainer>
  )
}
