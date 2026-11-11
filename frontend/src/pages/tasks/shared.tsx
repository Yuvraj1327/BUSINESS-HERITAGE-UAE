import { StatusBadge, type Status } from '@/components/common/status-badge'
import type { AuditEntry } from '@/schemas/finance'
import type { Task, TaskStatus, TaskTiming } from '@/schemas/tasks'
import { describeTaskChange, dueText } from './helpers'

/* Indicators are always colour + word (never colour alone). */
const STATUS: Record<TaskStatus, Status> = {
  'To Do': 'neutral',
  'In Progress': 'info',
  Done: 'success',
}
export const TaskStatusBadge = ({ status }: { status: TaskStatus }) => (
  <StatusBadge status={STATUS[status]}>{status}</StatusBadge>
)

const TIMING: Record<TaskTiming, { tone: Status; label: string }> = {
  overdue: { tone: 'danger', label: 'Overdue' },
  due_today: { tone: 'warning', label: 'Due Today' },
  upcoming: { tone: 'info', label: 'Upcoming' },
  no_due_date: { tone: 'neutral', label: 'No due date' },
  completed: { tone: 'success', label: 'Completed' },
}
export function TimingBadge({ task }: { task: Task }) {
  const t = TIMING[task.timing]
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <StatusBadge status={t.tone}>{t.label}</StatusBadge>
      {task.timing === 'overdue' || task.timing === 'upcoming' ? (
        <span className="text-xs text-muted-foreground">{dueText(task.days_to_due)}</span>
      ) : null}
    </span>
  )
}

export function TaskHistory({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">No history yet.</p>
  return (
    <ol className="space-y-3" aria-label="Task history">
      {entries.map((e) => (
        <li key={e.id} className="rounded-md border p-3 text-sm">
          <p className="font-medium">{describeTaskChange(e)}</p>
          <p className="text-xs text-muted-foreground">
            {new Intl.DateTimeFormat('en-GB', {
              dateStyle: 'medium',
              timeStyle: 'short',
              timeZone: 'Asia/Dubai',
            }).format(new Date(e.occurred_at))}{' '}
            · {e.actor_name ?? 'System'}
            {e.reason ? ` · Reason: ${e.reason}` : ''}
          </p>
        </li>
      ))}
    </ol>
  )
}
