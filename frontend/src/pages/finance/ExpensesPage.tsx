import { Ban, Eye, PiggyBank, Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { ErrorState } from '@/components/common/error-state'
import { Pagination } from '@/components/common/pagination'
import { ReasonDialog } from '@/components/common/reason-dialog'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { StatusBadge } from '@/components/common/status-badge'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { PageContainer } from '@/components/layout/page-container'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  useBalances,
  useCategories,
  useExpense,
  useExpenses,
  useSetSaving,
  useVoidExpense,
} from '@/hooks/use-finance'
import { PAY_ACCOUNTS, type Expense } from '@/schemas/finance'
import { dubaiToday, formatAED, formatDate } from '@/utils/format'
import { ExpenseDialog } from './ExpenseDialog'

const PAGE_SIZE = 25
const ALL = 'all'
const HEAD_OFFICE = 'head-office'

function ExpenseDetails({ id, onClose }: { id: string | null; onClose: () => void }) {
  const detail = useExpense(id)
  const e = detail.data?.expense
  return (
    <Dialog open={id !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Expense details</DialogTitle>
          <DialogDescription>Full record and its audit history.</DialogDescription>
        </DialogHeader>
        {detail.error ? (
          <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
        ) : !e ? (
          <p role="status">Loading…</p>
        ) : (
          <div className="space-y-4 text-sm">
            <dl className="grid grid-cols-2 gap-3">
              <div>
                <dt className="text-muted-foreground">Date</dt>
                <dd>{formatDate(e.expense_date)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Amount</dt>
                <dd className="font-medium">{formatAED(e.amount)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Category</dt>
                <dd>{e.category}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Branch</dt>
                <dd>{e.branch_name ?? 'All branches'}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Paid from</dt>
                <dd>{e.paid_from}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Saving</dt>
                <dd>{e.is_saving ? 'Yes' : 'No'}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Created by</dt>
                <dd>{e.created_by_name ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Status</dt>
                <dd>{e.voided ? `Voided: ${e.void_reason ?? ''}` : 'Active'}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-muted-foreground">Note</dt>
                <dd>{e.note ?? '—'}</dd>
              </div>
            </dl>
            <div>
              <h3 className="mb-2 font-medium">Audit history</h3>
              <ul className="space-y-2" aria-label="Audit history">
                {detail.data?.history.map((h) => (
                  <li key={h.id} className="rounded-md border px-3 py-2">
                    <span className="font-medium">{h.action}</span> by {h.actor_name ?? 'system'} ·{' '}
                    {new Date(h.occurred_at).toLocaleString('en-GB', { timeZone: 'Asia/Dubai' })}
                    {h.reason ? (
                      <span className="block text-muted-foreground">Reason: {h.reason}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function ExpensesPage() {
  const { branches } = useBranchContext()
  const categories = useCategories()
  const balances = useBalances()
  const start = balances.data?.tracking_start ?? undefined
  const notConfigured = balances.data?.status === 'not_configured'

  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [branch, setBranch] = useState(ALL)
  const [category, setCategory] = useState(ALL)
  const [source, setSource] = useState(ALL)
  const [saving, setSaving] = useState(ALL)
  const [page, setPage] = useState(1)
  const rangeInvalid = Boolean(from && to && from > to)

  const filters = {
    page,
    page_size: PAGE_SIZE,
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: to } : {}),
    ...(branch === HEAD_OFFICE
      ? { all_branches_only: true }
      : branch !== ALL
        ? { branch_id: branch }
        : {}),
    ...(category !== ALL ? { category_id: category } : {}),
    ...(source !== ALL ? { paid_from: source } : {}),
    ...(saving !== ALL ? { is_saving: saving === 'yes' } : {}),
  }
  const list = useExpenses(filters)
  const setFilter = (set: (v: string) => void) => (v: string) => {
    set(v)
    setPage(1)
  }

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Expense | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [voiding, setVoiding] = useState<Expense | null>(null)
  const [toggling, setToggling] = useState<Expense | null>(null)
  const voidExpense = useVoidExpense()
  const setSavingStatus = useSetSaving()

  const columns: DataTableColumn<Expense>[] = [
    { key: 'd', header: 'Date', cell: (r) => formatDate(r.expense_date) },
    { key: 'c', header: 'Category', cell: (r) => r.category },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name ?? 'All branches' },
    { key: 'a', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
    { key: 'p', header: 'Paid from', cell: (r) => r.paid_from },
    {
      key: 's',
      header: 'Type',
      cell: (r) =>
        r.voided ? (
          <StatusBadge status="neutral">Voided</StatusBadge>
        ) : r.is_saving ? (
          <StatusBadge status="info">Saving</StatusBadge>
        ) : (
          <StatusBadge status="success">Expense</StatusBadge>
        ),
    },
    { key: 'n', header: 'Note', cell: (r) => r.note ?? '—', className: 'max-w-48 truncate' },
    {
      key: 'x',
      header: 'Actions',
      cell: (r) => (
        <div className="flex flex-wrap gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDetailId(r.id)}
            aria-label={`View expense ${r.category} ${r.expense_date}`}
          >
            <Eye aria-hidden /> View
          </Button>
          {!r.voided ? (
            <Can module="expenses" action="update">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing(r)
                  setFormOpen(true)
                }}
                aria-label={`Edit expense ${r.category} ${r.expense_date}`}
              >
                <Pencil aria-hidden /> Edit
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setToggling(r)}
                aria-label={`${r.is_saving ? 'Unmark' : 'Mark'} as saving ${r.category} ${r.expense_date}`}
              >
                <PiggyBank aria-hidden /> {r.is_saving ? 'Unmark saving' : 'Mark saving'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setVoiding(r)}
                aria-label={`Delete expense ${r.category} ${r.expense_date}`}
              >
                <Ban aria-hidden /> Delete
              </Button>
            </Can>
          ) : null}
        </div>
      ),
    },
  ]

  const totals = list.data?.totals
  return (
    <PageContainer
      title="Expenses & Savings"
      description="Head office expenses and savings. Shop expenses are entered in the Daily Report."
      actions={
        <Can module="expenses" action="create">
          <Button
            onClick={() => {
              setEditing(null)
              setFormOpen(true)
            }}
            disabled={notConfigured}
          >
            <Plus aria-hidden /> New expense
          </Button>
        </Can>
      }
    >
      {notConfigured ? (
        <p
          role="status"
          className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
        >
          Opening balances are not configured yet, so expenses cannot be recorded. Set them under
          Opening Balances first.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3" aria-label="Expense totals">
        <StatCard
          label="Expenses (excl. savings)"
          isLoading={list.isLoading}
          value={totals ? formatAED(totals.excl_savings) : undefined}
          description="For the current filters"
        />
        <StatCard
          label="Savings"
          icon={PiggyBank}
          isLoading={list.isLoading}
          value={totals ? formatAED(totals.savings) : undefined}
          description="For the current filters"
        />
        <StatCard
          label="Total paid out"
          isLoading={list.isLoading}
          value={totals ? formatAED(totals.total) : undefined}
          description={totals ? `${totals.count} entries` : undefined}
        />
      </div>

      <SectionCard
        title="Expense list"
        description="Latest first. Voided entries are hidden from totals."
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormDatePicker
              label="From"
              value={from}
              min={start}
              max={to || dubaiToday()}
              onChange={(e) => setFilter(setFrom)(e.target.value)}
            />
            <FormDatePicker
              label="To"
              value={to}
              max={dubaiToday()}
              error={rangeInvalid ? 'Start date must not be after end date' : undefined}
              onChange={(e) => setFilter(setTo)(e.target.value)}
            />
            <FormSelect
              label="Branch"
              value={branch}
              onValueChange={setFilter(setBranch)}
              options={[
                { value: ALL, label: 'All' },
                { value: HEAD_OFFICE, label: 'All-branches entries only' },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
            <FormSelect
              label="Category"
              value={category}
              onValueChange={setFilter(setCategory)}
              options={[
                { value: ALL, label: 'All categories' },
                ...(categories.data ?? []).map((c) => ({ value: c.id, label: c.name })),
              ]}
            />
            <FormSelect
              label="Paid from"
              value={source}
              onValueChange={setFilter(setSource)}
              options={[
                { value: ALL, label: 'All sources' },
                ...PAY_ACCOUNTS.map((a) => ({ value: a, label: a })),
              ]}
            />
            <FormSelect
              label="Saving"
              value={saving}
              onValueChange={setFilter(setSaving)}
              options={[
                { value: ALL, label: 'Expenses and savings' },
                { value: 'yes', label: 'Savings only' },
                { value: 'no', label: 'Expenses only' },
              ]}
            />
          </div>
          <DataTable
            caption="Head office expenses"
            rows={rangeInvalid ? [] : list.data?.items}
            isLoading={list.isLoading}
            error={list.error}
            onRetry={() => void list.refetch()}
            getRowId={(r) => r.id}
            columns={columns}
            emptyTitle="No expenses match these filters"
            emptyDescription="Record a head office expense with New expense."
          />
          {list.data ? (
            <Pagination
              page={list.data.page}
              pageSize={list.data.page_size}
              total={list.data.total}
              noun="expenses"
              onPage={setPage}
            />
          ) : null}
        </div>
      </SectionCard>

      <ExpenseDialog open={formOpen} onOpenChange={setFormOpen} expense={editing} minDate={start} />
      <ExpenseDetails id={detailId} onClose={() => setDetailId(null)} />

      <ReasonDialog
        open={voiding !== null}
        onOpenChange={(o) => !o && setVoiding(null)}
        title="Delete this expense?"
        confirmLabel="Delete expense"
        isLoading={voidExpense.isPending}
        description={
          voiding
            ? `${voiding.category}, ${formatAED(voiding.amount)} on ${formatDate(voiding.expense_date)}. It is removed from all balances; the record stays in the audit log.`
            : null
        }
        onSubmit={async (reason) => {
          await voidExpense.mutateAsync({ id: (voiding as Expense).id, reason })
          toast.success('Expense deleted')
        }}
      />
      <ReasonDialog
        open={toggling !== null}
        onOpenChange={(o) => !o && setToggling(null)}
        title={toggling?.is_saving ? 'Unmark as saving?' : 'Mark as saving?'}
        confirmLabel={toggling?.is_saving ? 'Unmark saving' : 'Mark as saving'}
        destructive={false}
        isLoading={setSavingStatus.isPending}
        description={
          toggling
            ? `${toggling.category}, ${formatAED(toggling.amount)}. ${toggling.is_saving ? 'It will count as a normal expense again.' : 'It will count in Total Savings and leave normal expenses.'}`
            : null
        }
        onSubmit={async (reason) => {
          const t = toggling as Expense
          await setSavingStatus.mutateAsync({ id: t.id, is_saving: !t.is_saving, reason })
          toast.success(t.is_saving ? 'Unmarked as saving' : 'Marked as saving')
        }}
      />
    </PageContainer>
  )
}
