import { Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
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
import { useCompliance, useComplianceSummary, useUpdateExpiry } from '@/hooks/use-hr'
import type { ComplianceRow } from '@/schemas/hr'
import { formatDate } from '@/utils/format'
import { ActionDialog, EmploymentBadge, ExpiryBadge } from './shared'

const PAGE_SIZE = 15

function Section({ kind }: { kind: 'visas' | 'passports' }) {
  const one = kind === 'visas' ? 'visa' : 'passport'
  const label = kind === 'visas' ? 'Visa' : 'Passport'
  const { branches } = useBranchContext()
  const update = useUpdateExpiry()
  const [q, setQ] = useState('')
  const [branch, setBranch] = useState('all')
  const [bucket, setBucket] = useState('all')
  const [desc, setDesc] = useState(false)
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<ComplianceRow | null>(null)
  const list = useCompliance(kind, {
    page,
    page_size: PAGE_SIZE,
    sort: 'expiry',
    desc,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(branch !== 'all' ? { branch_id: branch } : {}),
    ...(bucket !== 'all' ? { bucket } : {}),
  })
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }

  const columns: DataTableColumn<ComplianceRow>[] = [
    {
      key: 'e',
      header: 'Employee',
      cell: (r) => (
        <Link
          to={`/employees/${r.employee_id}`}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {r.employee_name}
        </Link>
      ),
    },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name },
    {
      key: 'x',
      header: `${label} expiry`,
      cell: (r) => (r.expiry_date ? formatDate(r.expiry_date) : '—'),
    },
    {
      key: 's',
      header: 'Status',
      cell: (r) => <ExpiryBadge status={r.status} days={r.days_remaining} />,
    },
    {
      key: 'em',
      header: 'Employment',
      cell: (r) => <EmploymentBadge status={r.employment_status} />,
    },
    {
      key: 'a',
      header: 'Update',
      cell: (r) => (
        <Can module="visas_passports" action="update">
          {kind === 'visas' && r.status === 'cancelled' ? (
            <span className="text-xs text-muted-foreground">Cancelled</span>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setEditing(r)}
              aria-label={`Update ${one} expiry for ${r.employee_name}`}
            >
              Update
            </Button>
          )}
        </Can>
      ),
    },
  ]

  return (
    <SectionCard
      title={`${label}s`}
      description={
        kind === 'visas'
          ? 'Red: expired or within 30 days. Amber: within 90 days.'
          : 'Red: expired or within 30 days. Amber: within 180 days.'
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <FormInput
              label={`Search ${one}s`}
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
            label="Expiry period"
            value={bucket}
            onValueChange={reset(setBucket)}
            options={[
              { value: 'all', label: 'All records' },
              { value: 'expired', label: 'Expired' },
              { value: 'urgent', label: 'Urgent (within 30 days)' },
              {
                value: 'upcoming',
                label:
                  kind === 'visas' ? 'Upcoming (within 90 days)' : 'Upcoming (within 180 days)',
              },
              { value: 'normal', label: 'Valid' },
              { value: 'not_recorded', label: 'Not recorded' },
              ...(kind === 'visas' ? [{ value: 'cancelled', label: 'Visa cancelled' }] : []),
            ]}
          />
          <FormSelect
            label="Sort by expiry"
            value={desc ? 'latest' : 'nearest'}
            onValueChange={(v) => reset(setDesc)(v === 'latest')}
            options={[
              { value: 'nearest', label: 'Nearest expiry first' },
              { value: 'latest', label: 'Latest expiry first' },
            ]}
          />
        </div>
        <DataTable
          caption={`${label} records`}
          rows={list.data?.items}
          isLoading={list.isLoading}
          error={list.error}
          onRetry={() => void list.refetch()}
          getRowId={(r) => r.employee_id}
          columns={columns}
          emptyTitle={`No ${one} records found`}
          emptyDescription="Change the search or filters."
        />
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="records"
            onPage={setPage}
          />
        ) : null}
      </div>
      {editing ? (
        <ActionDialog
          open
          onOpenChange={(o) => !o && setEditing(null)}
          title={`Update ${one} expiry`}
          description={`${editing.employee_name}: only the expiry date is stored. The old and new dates are kept in the history.`}
          confirmLabel="Save expiry"
          dateLabel="New expiry date"
          dateDefault={editing.expiry_date ?? ''}
          reasonRequired={false}
          reasonLabel="Reason (optional)"
          onSubmit={async (v) => {
            await update.mutateAsync({
              id: editing.employee_id,
              kind: one,
              expiry_date: v.date,
              ...(v.reason ? { reason: v.reason } : {}),
            })
            toast.success(`${label} expiry updated`)
          }}
        />
      ) : null}
    </SectionCard>
  )
}

export function VisasPassportsPage() {
  const summary = useComplianceSummary()
  const s = summary.data
  const n = (v: number | undefined) => (v === undefined ? undefined : String(v))
  return (
    <PageContainer
      title="Visas & Passports"
      description="Expiry dates only: no passport or Emirates ID numbers are stored. Statuses come from the real dates in Dubai time. Owner only."
    >
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Visas</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Visa summary">
          <StatCard
            label="Visas Expired"
            isLoading={summary.isLoading}
            value={n(s?.visas.expired)}
          />
          <StatCard
            label="Visas Expiring ≤ 30 Days"
            isLoading={summary.isLoading}
            value={n(s?.visas_expiring_30)}
          />
          <StatCard
            label="Visas Upcoming (31–90 Days)"
            isLoading={summary.isLoading}
            value={n(s?.visas.upcoming)}
          />
          <StatCard
            label="Visas Cancelled"
            isLoading={summary.isLoading}
            value={n(s?.visas_cancelled)}
          />
        </div>
      </div>
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Passports</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Passport summary">
          <StatCard
            label="Passports Expired"
            isLoading={summary.isLoading}
            value={n(s?.passports.expired)}
          />
          <StatCard
            label="Passports Expiring ≤ 30 Days"
            isLoading={summary.isLoading}
            value={n(s?.passports_expiring_30)}
          />
          <StatCard
            label="Passports Under 6 Months"
            isLoading={summary.isLoading}
            value={n(s?.passports_under_6_months)}
            description="Expiring within 180 days"
          />
          <StatCard
            label="Passports Not Recorded"
            isLoading={summary.isLoading}
            value={n(s?.passports.not_recorded)}
          />
        </div>
      </div>
      <Section kind="visas" />
      <Section kind="passports" />
    </PageContainer>
  )
}
