import { AlertTriangle, Bell, CheckCheck, Info, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { Pagination } from '@/components/common/pagination'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import {
  useAcknowledge,
  useAlertFacets,
  useAlerts,
  useAlertSummary,
  useMarkRead,
  useReadAll,
  useRefreshAlerts,
} from '@/hooks/use-alerts'
import { toApiError } from '@/lib/errors'
import { SEVERITIES, type Alert, type AlertSeverity } from '@/schemas/alerts'
import type { AlertFilters } from '@/services/alerts.service'
import { formatDate } from '@/utils/format'
import { AlertStateBadge, SeverityBadge } from './shared'

const PAGE_SIZE = 25
const SEV_LABEL: Record<AlertSeverity, string> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Informational',
}

export function NotificationsPage() {
  const { branches } = useBranchContext()
  const summary = useAlertSummary()
  const facets = useAlertFacets()
  const read = useMarkRead()
  const ack = useAcknowledge()
  const readAll = useReadAll()
  const refresh = useRefreshAlerts()
  const [scope, setScope] = useState<'active' | 'history'>('active')
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('all')
  const [severity, setSeverity] = useState('all')
  const [branch, setBranch] = useState('all')
  const [module, setModule] = useState('all')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const filters: AlertFilters = {
    page,
    page_size: PAGE_SIZE,
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(kind !== 'all' ? { kind } : {}),
    ...(severity !== 'all' ? { severity: severity as AlertSeverity } : {}),
    ...(branch !== 'all' ? { branch_id: branch } : {}),
    ...(module !== 'all' ? { module } : {}),
    ...(status !== 'all' ? { status } : {}),
  }
  const list = useAlerts(scope, filters)
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }
  const s = summary.data
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn()
      toast.success(ok)
    } catch (e) {
      toast.error(toApiError(e).message)
    }
  }
  const statusOptions =
    scope === 'active'
      ? [
          { value: 'unread', label: 'Unread' },
          { value: 'read', label: 'Read' },
        ]
      : [
          { value: 'acknowledged', label: 'Acknowledged' },
          { value: 'resolved', label: 'Resolved (issue fixed)' },
        ]

  const columns: DataTableColumn<Alert>[] = [
    { key: 'sv', header: 'Severity', cell: (r) => <SeverityBadge severity={r.severity} /> },
    {
      key: 't',
      header: 'Alert',
      cell: (r) => (
        <span>
          <Link to={r.href} className="font-medium text-primary underline-offset-4 hover:underline">
            {r.type_label}
          </Link>
          <span className="block text-xs text-muted-foreground">{r.detail}</span>
        </span>
      ),
    },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name ?? '—' },
    { key: 'd', header: 'Due date', cell: (r) => (r.due_date ? formatDate(r.due_date) : '—') },
    { key: 'a', header: 'Raised', cell: (r) => formatDate(r.alert_date) },
    { key: 's', header: 'State', cell: (r) => <AlertStateBadge status={r.status} /> },
    {
      key: 'x',
      header: 'Actions',
      cell: (r) =>
        r.status === 'resolved' || r.status === 'acknowledged' ? null : (
          <span className="flex flex-wrap gap-2">
            {r.status === 'unread' ? (
              <Button
                size="sm"
                variant="outline"
                aria-label={`Mark read: ${r.type_label}`}
                onClick={() => void run(() => read.mutateAsync(r.id), 'Marked read')}
              >
                Mark read
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              aria-label={`Acknowledge: ${r.type_label}`}
              onClick={() => void run(() => ack.mutateAsync(r.id), 'Alert acknowledged')}
            >
              Acknowledge
            </Button>
          </span>
        ),
    },
  ]

  return (
    <PageContainer
      title="Notifications"
      description="Every alert, calculated from the real records. Owner only."
      actions={
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={refresh.isPending}
            onClick={() => void run(() => refresh.mutateAsync(), 'Alerts recalculated')}
          >
            <RefreshCw aria-hidden /> Refresh
          </Button>
          <Button
            variant="outline"
            disabled={readAll.isPending || !s || s.unread === 0}
            onClick={() => void run(() => readAll.mutateAsync(), 'All alerts marked read')}
          >
            <CheckCheck aria-hidden /> Mark all read
          </Button>
        </div>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Alert summary">
        <StatCard
          label="Total Active"
          icon={Bell}
          isLoading={summary.isLoading}
          value={s ? String(s.total_active) : undefined}
        />
        <StatCard
          label="Critical"
          icon={ShieldAlert}
          isLoading={summary.isLoading}
          value={s ? String(s.critical) : undefined}
        />
        <StatCard
          label="Warning"
          icon={AlertTriangle}
          isLoading={summary.isLoading}
          value={s ? String(s.warning) : undefined}
        />
        <StatCard
          label="Informational"
          icon={Info}
          isLoading={summary.isLoading}
          value={s ? String(s.info) : undefined}
        />
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Alert list">
          {(['active', 'history'] as const).map((v) => (
            <Button
              key={v}
              size="sm"
              variant={scope === v ? 'default' : 'outline'}
              aria-pressed={scope === v}
              onClick={() => {
                setScope(v)
                setStatus('all')
                setPage(1)
              }}
            >
              {v === 'active' ? 'Active' : 'History'}
            </Button>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div className="relative">
            <FormInput
              label="Search"
              type="search"
              placeholder="Title, detail or branch"
              value={q}
              onChange={(e) => reset(setQ)(e.target.value)}
            />
            <Search
              className="pointer-events-none absolute right-3 bottom-2.5 size-4 text-muted-foreground"
              aria-hidden
            />
          </div>
          <FormSelect
            label="Type"
            value={kind}
            onValueChange={reset(setKind)}
            options={[
              { value: 'all', label: 'All types' },
              ...(facets.data?.kinds ?? []).map(([v, l]) => ({ value: v, label: l })),
            ]}
          />
          <FormSelect
            label="Module"
            value={module}
            onValueChange={reset(setModule)}
            options={[
              { value: 'all', label: 'All modules' },
              ...(facets.data?.modules ?? []).map(([v, l]) => ({ value: v, label: l })),
            ]}
          />
          <FormSelect
            label="Severity"
            value={severity}
            onValueChange={reset(setSeverity)}
            options={[
              { value: 'all', label: 'All severities' },
              ...SEVERITIES.map((v) => ({ value: v, label: SEV_LABEL[v] })),
            ]}
          />
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
            label="State"
            value={status}
            onValueChange={reset(setStatus)}
            options={[{ value: 'all', label: 'Any state' }, ...statusOptions]}
          />
        </div>
        <SectionCard
          title={scope === 'active' ? 'Active alerts' : 'Alert history'}
          contentClassName="p-0 sm:p-0"
        >
          <DataTable
            caption={scope === 'active' ? 'Active alerts' : 'Alert history'}
            rows={list.data?.items}
            isLoading={list.isLoading}
            error={list.error}
            onRetry={() => void list.refetch()}
            getRowId={(r) => r.id}
            columns={columns}
            emptyTitle={scope === 'active' ? 'No active alerts' : 'No alert history yet'}
            emptyDescription={
              scope === 'active'
                ? 'Nothing needs attention right now, or the filters match nothing.'
                : 'Acknowledged alerts and alerts whose issue was fixed appear here.'
            }
          />
        </SectionCard>
        {list.data ? (
          <Pagination
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            noun="alerts"
            onPage={setPage}
          />
        ) : null}
      </div>
    </PageContainer>
  )
}
