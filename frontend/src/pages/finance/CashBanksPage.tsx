import { ArrowLeftRight, Ban, Banknote, Landmark, PiggyBank, Wallet } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { DataTable, type DataTableColumn } from '@/components/common/data-table'
import { EmptyState } from '@/components/common/empty-state'
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
  useAccountsReport,
  useBalances,
  useBranchCash,
  useLedger,
  useSettlements,
  useTransfers,
  useVoidSettlement,
  useVoidTransfer,
} from '@/hooks/use-finance'
import {
  LEDGER_ACCOUNTS,
  type AccountsReport,
  type BranchCashReport,
  type LedgerRow,
  type Settlement,
  type Transfer,
} from '@/schemas/finance'
import { dubaiToday, formatAED, formatDate } from '@/utils/format'
import { SettlementDialog, TransferDialog } from './TransferForms'

const PAGE_SIZE = 25
const ALL = 'all'

const signed = (v: string) => (Number(v) > 0 ? `+${formatAED(v)}` : formatAED(v))

const ledgerColumns: DataTableColumn<LedgerRow>[] = [
  { key: 'date', header: 'Date', cell: (r) => formatDate(r.txn_date) },
  { key: 'type', header: 'Type', cell: (r) => r.txn_type },
  { key: 'branch', header: 'Branch', cell: (r) => r.branch_name ?? 'Head office' },
  { key: 'account', header: 'Account', cell: (r) => r.account },
  {
    key: 'amount',
    header: 'Amount',
    align: 'right',
    cell: (r) => (
      <span className={Number(r.amount) < 0 ? 'text-destructive' : undefined}>
        {signed(r.amount)}
      </span>
    ),
  },
  {
    key: 'desc',
    header: 'Description / reference',
    cell: (r) => r.description ?? '—',
    className: 'max-w-64 truncate',
  },
  { key: 'by', header: 'Created by', cell: (r) => r.created_by_name ?? 'System' },
]

function AccountsTable({ report }: { report: AccountsReport }) {
  return (
    <DataTable
      caption="Account movements for the selected period"
      rows={report.accounts}
      getRowId={(r) => r.account}
      columns={[
        {
          key: 'a',
          header: 'Account',
          cell: (r) => <span className="font-medium">{r.account}</span>,
        },
        { key: 'o', header: 'Opening', align: 'right', cell: (r) => formatAED(r.opening) },
        { key: 'i', header: 'Incoming', align: 'right', cell: (r) => formatAED(r.incoming) },
        { key: 'u', header: 'Outgoing', align: 'right', cell: (r) => formatAED(r.outgoing) },
        {
          key: 'c',
          header: 'Closing',
          align: 'right',
          cell: (r) => <strong>{formatAED(r.closing)}</strong>,
        },
      ]}
    />
  )
}

function BranchTable({ report }: { report: BranchCashReport }) {
  return (
    <DataTable
      caption="Cash balance by branch"
      rows={report.rows}
      getRowId={(r) => r.branch_id ?? 'head-office'}
      columns={[
        {
          key: 'b',
          header: 'Branch',
          cell: (r) => <span className="font-medium">{r.branch_name}</span>,
        },
        { key: 'o', header: 'Opening', align: 'right', cell: (r) => formatAED(r.opening) },
        { key: 'i', header: 'Incoming', align: 'right', cell: (r) => formatAED(r.incoming) },
        { key: 'u', header: 'Outgoing', align: 'right', cell: (r) => formatAED(r.outgoing) },
        {
          key: 'c',
          header: 'Closing',
          align: 'right',
          cell: (r) => <strong>{formatAED(r.closing)}</strong>,
        },
      ]}
    />
  )
}

export function CashBanksPage() {
  const { branches } = useBranchContext()
  const balances = useBalances()
  const configured = balances.data?.status === 'ok'
  const start = balances.data?.tracking_start ?? undefined

  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [account, setAccount] = useState(ALL)
  const [branch, setBranch] = useState(ALL)
  const [page, setPage] = useState(1)
  const rangeInvalid = Boolean(from && to && from > to)
  const ledgerFilters = {
    page,
    page_size: PAGE_SIZE,
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: to } : {}),
    ...(account !== ALL ? { account } : {}),
    ...(branch !== ALL ? { branch_id: branch } : {}),
  }
  const ledger = useLedger(ledgerFilters, configured && !rangeInvalid)
  const accounts = useAccountsReport(from, to, configured && !rangeInvalid)
  const branchCash = useBranchCash()
  const transfers = useTransfers()
  const settlements = useSettlements()
  const voidTransfer = useVoidTransfer()
  const voidSettlement = useVoidSettlement()

  const [transferOpen, setTransferOpen] = useState(false)
  const [settleOpen, setSettleOpen] = useState(false)
  const [voidingTransfer, setVoidingTransfer] = useState<Transfer | null>(null)
  const [voidingSettlement, setVoidingSettlement] = useState<Settlement | null>(null)

  if (balances.error)
    return (
      <PageContainer title="Cash & Banks">
        <ErrorState error={balances.error} onRetry={() => void balances.refetch()} />
      </PageContainer>
    )

  if (balances.data && !configured)
    return (
      <PageContainer
        title="Cash & Banks"
        description="Cash in hand, bank balances, POS and savings."
      >
        <EmptyState
          icon={Landmark}
          title="Opening balances are not configured"
          description="Set the starting balances first. Until then no cash or bank figure is shown, so nothing is guessed."
          action={
            <Button asChild>
              <Link to="/opening-balances">Set opening balances</Link>
            </Button>
          }
        />
      </PageContainer>
    )

  const b = balances.data
  const loading = balances.isLoading
  const money = (v: string | null | undefined) => (v == null ? undefined : formatAED(v))
  const resetPage =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v)
      setPage(1)
    }

  const transferCols: DataTableColumn<Transfer>[] = [
    { key: 'd', header: 'Date', cell: (r) => formatDate(r.transfer_date) },
    { key: 'f', header: 'From → To', cell: (r) => `${r.from_account} → ${r.to_account}` },
    { key: 'b', header: 'Branch', cell: (r) => r.branch_name ?? '—' },
    { key: 'a', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
    { key: 'r', header: 'Reference', cell: (r) => r.reference ?? '—' },
    {
      key: 's',
      header: 'Status',
      cell: (r) =>
        r.voided ? (
          <StatusBadge status="neutral">Voided</StatusBadge>
        ) : (
          <Can module="cash_banks" action="update">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setVoidingTransfer(r)}
              aria-label={`Void transfer ${r.from_account} to ${r.to_account} ${r.transfer_date}`}
            >
              <Ban aria-hidden /> Void
            </Button>
          </Can>
        ),
    },
  ]
  const settleCols: DataTableColumn<Settlement>[] = [
    { key: 'd', header: 'Date', cell: (r) => formatDate(r.settlement_date) },
    { key: 'b', header: 'Bank', cell: (r) => r.bank },
    { key: 'a', header: 'Amount', align: 'right', cell: (r) => formatAED(r.amount) },
    { key: 'r', header: 'Reference', cell: (r) => r.reference ?? '—' },
    {
      key: 's',
      header: 'Status',
      cell: (r) =>
        r.voided ? (
          <StatusBadge status="neutral">Voided</StatusBadge>
        ) : (
          <Can module="cash_banks" action="update">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setVoidingSettlement(r)}
              aria-label={`Void POS settlement ${r.settlement_date}`}
            >
              <Ban aria-hidden /> Void
            </Button>
          </Can>
        ),
    },
  ]

  return (
    <PageContainer
      title="Cash & Banks"
      description={
        start
          ? `Balances are calculated from the opening balances. Tracking started ${formatDate(start)}.`
          : 'Balances are calculated from the opening balances.'
      }
      actions={
        <Can module="cash_banks" action="create">
          <Button variant="outline" onClick={() => setSettleOpen(true)}>
            <Banknote aria-hidden /> POS settlement
          </Button>
          <Button onClick={() => setTransferOpen(true)}>
            <ArrowLeftRight aria-hidden /> New transfer
          </Button>
        </Can>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Balances">
        <StatCard
          label="Total Cash + Bank"
          icon={Wallet}
          isLoading={loading}
          value={money(b?.total_cash_bank)}
          description="Cash + ENBD + ADCB (unsettled POS excluded)"
        />
        <StatCard
          label="Cash in Hand"
          icon={Banknote}
          isLoading={loading}
          value={money(b?.cash_in_hand)}
        />
        <StatCard label="ENBD" icon={Landmark} isLoading={loading} value={money(b?.enbd)} />
        <StatCard label="ADCB" icon={Landmark} isLoading={loading} value={money(b?.adcb)} />
        <StatCard
          label="POS Pending"
          icon={Wallet}
          isLoading={loading}
          value={money(b?.pos_pending)}
          description="Card sales not yet paid out by the provider"
        />
        <StatCard
          label="Total Savings"
          icon={PiggyBank}
          isLoading={loading}
          value={money(b?.total_savings)}
        />
      </div>

      <SectionCard
        title="Branch-wise cash"
        description="Cash in hand at each branch. The head-office line is cash paid out for expenses not tied to a branch (it can show a negative closing figure: that cash comes out of the pooled total). The rows add up to Cash in Hand."
      >
        {branchCash.data ? (
          <BranchTable report={branchCash.data} />
        ) : (
          <DataTable
            caption="Cash balance by branch"
            rows={undefined}
            isLoading={branchCash.isLoading}
            error={branchCash.error}
            onRetry={() => void branchCash.refetch()}
            getRowId={() => ''}
            columns={[]}
          />
        )}
      </SectionCard>

      <SectionCard
        title="Account movements"
        description="Opening, incoming, outgoing and closing for the period below. ENBD, ADCB and POS Pending are listed with Cash."
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormDatePicker
              label="From"
              value={from}
              min={start}
              max={to || dubaiToday()}
              onChange={(e) => resetPage(setFrom)(e.target.value)}
            />
            <FormDatePicker
              label="To"
              value={to}
              max={dubaiToday()}
              error={rangeInvalid ? 'Start date must not be after end date' : undefined}
              onChange={(e) => resetPage(setTo)(e.target.value)}
            />
          </div>
          {accounts.data ? (
            <AccountsTable report={accounts.data} />
          ) : (
            <DataTable
              caption="Account movements"
              rows={undefined}
              isLoading={accounts.isLoading}
              error={accounts.error}
              onRetry={() => void accounts.refetch()}
              getRowId={() => ''}
              columns={[]}
            />
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Transaction history"
        description="Every cash and bank movement, newest first. Daily-report amounts appear once."
      >
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Account filter">
            {[ALL, ...LEDGER_ACCOUNTS].map((a) => (
              <Button
                key={a}
                size="sm"
                variant={account === a ? 'default' : 'outline'}
                aria-pressed={account === a}
                onClick={() => resetPage(setAccount)(a)}
              >
                {a === ALL
                  ? 'All accounts'
                  : a === 'POS Pending'
                    ? 'POS collections & settlements'
                    : `${a} movements`}
              </Button>
            ))}
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormSelect
              label="Branch"
              value={branch}
              onValueChange={resetPage(setBranch)}
              options={[
                { value: ALL, label: 'All branches' },
                ...branches.map((x) => ({ value: x.id, label: x.name })),
              ]}
            />
          </div>
          <DataTable
            caption="Cash and bank transaction history"
            rows={rangeInvalid ? [] : ledger.data?.items}
            isLoading={ledger.isLoading}
            error={ledger.error}
            onRetry={() => void ledger.refetch()}
            getRowId={(r) => `${r.source_id}-${r.account}-${r.txn_type}`}
            columns={ledgerColumns}
            emptyTitle="No transactions for these filters"
          />
          {ledger.data ? (
            <p className="text-sm text-muted-foreground">
              Incoming {formatAED(ledger.data.total_incoming)} · Outgoing{' '}
              {formatAED(ledger.data.total_outgoing)}
            </p>
          ) : null}
          {ledger.data ? (
            <Pagination
              page={ledger.data.page}
              pageSize={ledger.data.page_size}
              total={ledger.data.total}
              noun="transactions"
              onPage={setPage}
            />
          ) : null}
        </div>
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Recent transfers">
          <DataTable
            caption="Recent transfers"
            rows={transfers.data}
            isLoading={transfers.isLoading}
            error={transfers.error}
            onRetry={() => void transfers.refetch()}
            getRowId={(r) => r.id}
            columns={transferCols}
            emptyTitle="No transfers yet"
          />
        </SectionCard>
        <SectionCard title="POS settlements">
          <DataTable
            caption="POS settlements"
            rows={settlements.data}
            isLoading={settlements.isLoading}
            error={settlements.error}
            onRetry={() => void settlements.refetch()}
            getRowId={(r) => r.id}
            columns={settleCols}
            emptyTitle="No POS settlements yet"
          />
        </SectionCard>
      </div>

      <TransferDialog open={transferOpen} onOpenChange={setTransferOpen} minDate={start} />
      <SettlementDialog open={settleOpen} onOpenChange={setSettleOpen} minDate={start} />

      <ReasonDialog
        open={voidingTransfer !== null}
        onOpenChange={(o) => !o && setVoidingTransfer(null)}
        title="Void this transfer?"
        confirmLabel="Void transfer"
        isLoading={voidTransfer.isPending}
        description={
          voidingTransfer
            ? `${voidingTransfer.from_account} → ${voidingTransfer.to_account}, ${formatAED(voidingTransfer.amount)}. Both sides are reversed together.`
            : null
        }
        onSubmit={async (reason) => {
          await voidTransfer.mutateAsync({ id: (voidingTransfer as Transfer).id, reason })
          toast.success('Transfer voided')
        }}
      />
      <ReasonDialog
        open={voidingSettlement !== null}
        onOpenChange={(o) => !o && setVoidingSettlement(null)}
        title="Void this POS settlement?"
        confirmLabel="Void settlement"
        isLoading={voidSettlement.isPending}
        description={
          voidingSettlement
            ? `${voidingSettlement.bank}, ${formatAED(voidingSettlement.amount)}. The amount returns to POS pending.`
            : null
        }
        onSubmit={async (reason) => {
          await voidSettlement.mutateAsync({ id: (voidingSettlement as Settlement).id, reason })
          toast.success('POS settlement voided')
        }}
      />
    </PageContainer>
  )
}
