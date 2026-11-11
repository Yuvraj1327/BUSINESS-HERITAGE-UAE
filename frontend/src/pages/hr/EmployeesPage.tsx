import {
  AlertTriangle,
  Banknote,
  Plane,
  Plus,
  Search,
  UserCheck,
  UserMinus,
  UserX,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import { useEmployees, useEmployeeSummary, useLeaveSummary } from '@/hooks/use-hr'
import { EMPLOYMENT_STATUSES, type Employee, type EmploymentStatus } from '@/schemas/hr'
import type { EmployeeFilters } from '@/services/hr.service'
import { formatAED, formatDate } from '@/utils/format'
import { EmployeeDialog } from './EmployeeDialog'
import { EmploymentBadge, ExpiryBadge, LeaveBadge } from './shared'

const PAGE_SIZE = 25
const SORTS: { value: string; label: string; sort: EmployeeFilters['sort']; desc: boolean }[] = [
  { value: 'name', label: 'Name (A–Z)', sort: 'name', desc: false },
  { value: 'branch', label: 'Branch', sort: 'branch', desc: false },
  { value: 'salary', label: 'Highest salary', sort: 'salary', desc: true },
  { value: 'status', label: 'Status', sort: 'status', desc: false },
  { value: 'created', label: 'Newest first', sort: 'created', desc: true },
]

export function EmployeesPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { branches } = useBranchContext()
  const summary = useEmployeeSummary()
  const leave = useLeaveSummary()
  const initial = params.get('status')
  const [q, setQ] = useState('')
  const [branch, setBranch] = useState('all')
  const [status, setStatus] = useState(
    EMPLOYMENT_STATUSES.includes(initial as EmploymentStatus) ? (initial as string) : 'all',
  )
  const [sortKey, setSortKey] = useState('name')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const sort = SORTS.find((s) => s.value === sortKey) ?? SORTS[0]!

  const filters: EmployeeFilters = {
    page,
    page_size: PAGE_SIZE,
    sort: sort.sort,
    desc: sort.desc,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(branch !== 'all' ? { branch_id: branch } : {}),
    ...(status !== 'all' ? { status: status as EmploymentStatus } : {}),
  }
  const list = useEmployees(filters)
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }
  const s = summary.data

  const columns: DataTableColumn<Employee>[] = [
    {
      key: 'n',
      header: 'Employee',
      cell: (r) => (
        <Link
          to={`/employees/${r.id}`}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {r.full_name}
        </Link>
      ),
    },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name },
    { key: 'r', header: 'Role', cell: (r) => r.role_title ?? '—' },
    {
      key: 's',
      header: 'Salary',
      align: 'right',
      cell: (r) => formatAED(r.monthly_salary),
    },
    {
      key: 'st',
      header: 'Status',
      cell: (r) => (
        <span className="inline-flex flex-wrap items-center gap-2">
          <EmploymentBadge status={r.status} />
          {r.leave && r.leave.state !== 'on_leave' && r.leave.state !== 'visa_cancelled' ? (
            <LeaveBadge state={r.leave.state} />
          ) : null}
        </span>
      ),
    },
    {
      key: 'v',
      header: 'Visa',
      cell: (r) => <ExpiryBadge status={r.visa_status} days={r.visa_days_remaining} />,
    },
    {
      key: 'p',
      header: 'Passport',
      cell: (r) => <ExpiryBadge status={r.passport_status} days={r.passport_days_remaining} />,
    },
  ]

  const watch = leave.data?.items ?? []
  const watchColumns: DataTableColumn<Employee>[] = [
    {
      key: 'n',
      header: 'Employee',
      cell: (r) => (
        <Link to={`/employees/${r.id}`} className="font-medium text-primary hover:underline">
          {r.full_name}
        </Link>
      ),
    },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name },
    {
      key: 'ls',
      header: 'Leave start',
      cell: (r) => (r.leave ? formatDate(r.leave.leave_start) : '—'),
    },
    {
      key: 'd',
      header: 'Days on leave',
      align: 'right',
      cell: (r) => r.leave?.days_on_leave ?? '—',
    },
    {
      key: 'l',
      header: 'Six-month limit',
      cell: (r) => (r.leave ? formatDate(r.leave.limit_date) : '—'),
    },
    {
      key: 'rem',
      header: 'Days remaining',
      align: 'right',
      cell: (r) => (r.leave && r.leave.days_remaining >= 0 ? r.leave.days_remaining : '—'),
    },
    {
      key: 'st',
      header: 'Leave status',
      cell: (r) => (r.leave ? <LeaveBadge state={r.leave.state} /> : null),
    },
  ]

  return (
    <PageContainer
      title="Employees"
      description="Staff records, salaries, leave and visa status. Owner only."
      actions={
        <Can module="employees" action="create">
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden /> Add employee
          </Button>
        </Can>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5" aria-label="Employee summary">
        <StatCard
          label="Total Active Employees"
          icon={UserCheck}
          isLoading={summary.isLoading}
          value={s ? String(s.total_active) : undefined}
        />
        <StatCard
          label="Currently on Leave"
          icon={Plane}
          isLoading={summary.isLoading}
          value={s ? String(s.on_leave) : undefined}
        />
        <StatCard
          label="Close to Six-Month Leave Limit"
          icon={AlertTriangle}
          isLoading={summary.isLoading}
          value={s ? String(s.close_to_limit) : undefined}
          description="Limit within 30 days"
        />
        <StatCard
          label="Visa Cancelled"
          icon={UserX}
          isLoading={summary.isLoading}
          value={s ? String(s.visa_cancelled) : undefined}
        />
        <StatCard
          label="Monthly Payroll Total"
          icon={Banknote}
          isLoading={summary.isLoading}
          value={s ? formatAED(s.monthly_payroll) : undefined}
          description={
            s
              ? `Current salaries of ${s.payroll_employees} active employees. Not proof of payment.`
              : undefined
          }
        />
      </div>

      {watch.length > 0 ? (
        <SectionCard
          title="Leave watch"
          description="Employees whose six-month leave limit is within 30 days, reached, or passed. Six months are calendar months, not 180 days."
        >
          <DataTable
            caption="Leave watch"
            rows={watch}
            getRowId={(r) => r.id}
            columns={watchColumns}
            emptyTitle="No one near the limit"
            emptyIcon={UserMinus}
          />
        </SectionCard>
      ) : null}

      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <FormInput
              label="Search"
              type="search"
              placeholder="Employee name"
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
              ...branches.map((b) => ({ value: b.id, label: b.name })),
            ]}
          />
          <FormSelect
            label="Status"
            value={status}
            onValueChange={reset(setStatus)}
            options={[
              { value: 'all', label: 'All statuses' },
              ...EMPLOYMENT_STATUSES.map((x) => ({ value: x, label: x })),
            ]}
          />
          <FormSelect
            label="Sort by"
            value={sortKey}
            onValueChange={reset(setSortKey)}
            options={SORTS.map((x) => ({ value: x.value, label: x.label }))}
          />
        </div>
        <DataTable
          caption="Employees"
          rows={list.data?.items}
          isLoading={list.isLoading}
          error={list.error}
          onRetry={() => void list.refetch()}
          getRowId={(r) => r.id}
          columns={columns}
          emptyTitle="No employees found"
          emptyDescription="Add an employee, or change the search and filters."
        />
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="employees"
            onPage={setPage}
          />
        ) : null}
      </div>

      <EmployeeDialog
        open={adding}
        onOpenChange={setAdding}
        onSaved={(id) => navigate(`/employees/${id}`)}
      />
    </PageContainer>
  )
}
