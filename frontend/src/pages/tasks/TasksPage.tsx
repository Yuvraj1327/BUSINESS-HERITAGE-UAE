import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ListChecks,
  Loader,
  Plus,
  Search,
  Timer,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useAssignees, useTasks, useTaskSummary } from '@/hooks/use-tasks'
import { TASK_STATUSES, type Task, type TaskStatus } from '@/schemas/tasks'
import type { TaskFilters } from '@/services/tasks.service'
import { TaskDialog } from './TaskDialog'
import { dueLabel } from './helpers'
import { TaskStatusBadge, TimingBadge } from './shared'

const PAGE_SIZE = 25
const VIEWS = [
  { value: 'all', label: 'All tasks' },
  { value: 'open', label: 'Open' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'today', label: 'Due today' },
  { value: 'week', label: 'Due within 7 days' },
  { value: 'completed', label: 'Completed' },
] as const
const SORTS: { value: string; label: string; sort: TaskFilters['sort']; desc: boolean }[] = [
  { value: 'due', label: 'Due date (soonest first)', sort: 'due', desc: false },
  { value: 'due_desc', label: 'Due date (latest first)', sort: 'due', desc: true },
  { value: 'created_desc', label: 'Newest created', sort: 'created', desc: true },
  { value: 'created', label: 'Oldest created', sort: 'created', desc: false },
  { value: 'title', label: 'Title (A–Z)', sort: 'title', desc: false },
]

export function TasksPage() {
  const [params] = useSearchParams()
  const { branches } = useBranchContext()
  const summary = useTaskSummary()
  const assignees = useAssignees()
  const initialView = params.get('view')
  const [view, setView] = useState<string>(
    VIEWS.some((v) => v.value === initialView) ? (initialView as string) : 'all',
  )
  const [q, setQ] = useState('')
  const [branch, setBranch] = useState('all')
  const [status, setStatus] = useState('all')
  const [assignee, setAssignee] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [sortKey, setSortKey] = useState('due')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const sort = SORTS.find((s) => s.value === sortKey) ?? SORTS[0]!
  const filters: TaskFilters = {
    page,
    page_size: PAGE_SIZE,
    sort: sort.sort,
    desc: sort.desc,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(branch === 'none' ? { all_branches: true } : branch !== 'all' ? { branch_id: branch } : {}),
    ...(status !== 'all' ? { status: status as TaskStatus } : {}),
    ...(assignee === 'none'
      ? { unassigned: true }
      : assignee !== 'all'
        ? { assignee_id: assignee }
        : {}),
    ...(view !== 'all' ? { view: view as NonNullable<TaskFilters['view']> } : {}),
    ...(from ? { due_from: from } : {}),
    ...(to ? { due_to: to } : {}),
  }
  const list = useTasks(filters)
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }
  const s = summary.data
  const card = (label: string, icon: typeof ListChecks, n: number | undefined) => (
    <StatCard
      label={label}
      icon={icon}
      isLoading={summary.isLoading}
      value={s ? String(n) : undefined}
    />
  )

  const columns: DataTableColumn<Task>[] = [
    {
      key: 't',
      header: 'Title',
      cell: (r) => (
        <Link
          to={`/tasks/${r.id}`}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {r.title}
        </Link>
      ),
    },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name },
    { key: 'a', header: 'Assigned to', cell: (r) => r.assignee_name },
    { key: 'd', header: 'Due date', cell: (r) => dueLabel(r.due_date) },
    { key: 'tm', header: 'Timing', cell: (r) => <TimingBadge task={r} /> },
    { key: 's', header: 'Status', cell: (r) => <TaskStatusBadge status={r.status} /> },
  ]

  return (
    <PageContainer
      title="Tasks"
      description="Follow up work across branches. Owner only."
      actions={
        <Can module="tasks" action="create">
          <Button onClick={() => setCreating(true)}>
            <Plus aria-hidden /> New task
          </Button>
        </Can>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Task summary">
        {card('Total Tasks', ListChecks, s?.total)}
        {card('To Do', Timer, s?.to_do)}
        {card('In Progress', Loader, s?.in_progress)}
        {card('Completed', CheckCircle2, s?.done)}
        {card('Overdue', AlertTriangle, s?.overdue)}
        {card('Due Today', CalendarClock, s?.due_today)}
        {card('Due Within 7 Days', CalendarClock, s?.due_7)}
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Quick views">
          {VIEWS.map((v) => (
            <Button
              key={v.value}
              size="sm"
              variant={view === v.value ? 'default' : 'outline'}
              aria-pressed={view === v.value}
              onClick={() => reset(setView)(v.value)}
            >
              {v.label}
            </Button>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <FormInput
              label="Search"
              type="search"
              placeholder="Title or description"
              value={q}
              onChange={(e) => reset(setQ)(e.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 bottom-2.5 size-4 text-muted-foreground"
              aria-hidden
            />
          </div>
          <FormSelect
            label="Branch"
            value={branch}
            onValueChange={reset(setBranch)}
            options={[
              { value: 'all', label: 'All branches' },
              { value: 'none', label: 'All Branches tasks only' },
              ...branches.map((b) => ({ value: b.id, label: b.name })),
            ]}
          />
          <FormSelect
            label="Status"
            value={status}
            onValueChange={reset(setStatus)}
            options={[
              { value: 'all', label: 'All statuses' },
              ...TASK_STATUSES.map((x) => ({ value: x, label: x })),
            ]}
          />
          <FormSelect
            label="Assigned to"
            value={assignee}
            onValueChange={reset(setAssignee)}
            options={[
              { value: 'all', label: 'Anyone' },
              { value: 'none', label: 'Unassigned' },
              ...(assignees.data ?? []).map((a) => ({ value: a.id, label: a.name })),
            ]}
          />
          <FormDatePicker
            label="Due from"
            value={from}
            onChange={(e) => reset(setFrom)(e.target.value)}
          />
          <FormDatePicker
            label="Due to"
            value={to}
            onChange={(e) => reset(setTo)(e.target.value)}
          />
          <FormSelect
            label="Sort by"
            value={sortKey}
            onValueChange={reset(setSortKey)}
            options={SORTS.map((x) => ({ value: x.value, label: x.label }))}
          />
        </div>
        <SectionCard title="Tasks" contentClassName="p-0 sm:p-0">
          <DataTable
            caption="Tasks"
            rows={list.data?.items}
            isLoading={list.isLoading}
            error={list.error}
            onRetry={() => void list.refetch()}
            getRowId={(r) => r.id}
            columns={columns}
            emptyTitle="No tasks found"
            emptyDescription="Create a task, or change the filters to see more."
          />
        </SectionCard>
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="tasks"
            onPage={setPage}
          />
        ) : null}
      </div>
      <TaskDialog open={creating} onOpenChange={setCreating} />
    </PageContainer>
  )
}
