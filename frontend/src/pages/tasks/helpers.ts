import type { AuditEntry } from '@/schemas/finance'
import { formatDate } from '@/utils/format'

export function dueText(days: number | null): string {
  if (days === null) return ''
  if (days < 0) return `${-days} day${days === -1 ? '' : 's'} overdue`
  if (days === 0) return 'Due today'
  return `Due in ${days} day${days === 1 ? '' : 's'}`
}
const LABEL: Record<string, string> = {
  title: 'Title',
  description: 'Description',
  branch_id: 'Branch',
  assignee_id: 'Assigned to',
  due_date: 'Due date',
  status: 'Status',
  notes: 'Notes',
  completed_at: 'Completed',
}
const HIDDEN = new Set([
  'id',
  'created_at',
  'created_by',
  'updated_at',
  'updated_by',
  'completed_by',
])
const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))
export function describeTaskChange(e: AuditEntry): string {
  if (e.action === 'INSERT') return 'Task created'
  const o = e.old_values ?? {}
  const n = e.new_values ?? {}
  const parts = Object.keys(n)
    .filter((k) => !HIDDEN.has(k) && JSON.stringify(o[k]) !== JSON.stringify(n[k]))
    .map((k) =>
      k === 'branch_id' || k === 'assignee_id'
        ? `${LABEL[k]} changed`
        : k === 'completed_at'
          ? n[k]
            ? 'Marked completed'
            : 'Reopened'
          : `${LABEL[k] ?? k}: ${show(o[k])} → ${show(n[k])}`,
    )
  return parts.join('; ') || 'No visible change'
}

export const dueLabel = (d: string | null) => (d ? formatDate(d) : '—')
