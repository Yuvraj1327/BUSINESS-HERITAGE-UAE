import { AlertTriangle, ChevronLeft, ChevronRight, Info } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { DataTable } from '@/components/common/data-table'
import { ErrorState } from '@/components/common/error-state'
import { SectionCard } from '@/components/common/section-card'
import { StatCard } from '@/components/common/stat-card'
import { StatusBadge } from '@/components/common/status-badge'
import { PageContainer } from '@/components/layout/page-container'
import { MissingPanel } from '@/components/reporting/missing-panel'
import { Button } from '@/components/ui/button'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { useAlertSummary } from '@/hooks/use-alerts'
import { useOwnerDashboard } from '@/hooks/use-reports'
import { SeverityBadge } from '@/pages/alerts/shared'
import type { OwnerDashboard as OwnerDashboardData } from '@/schemas/dashboard'
import { addDays, addMonths, formatMonth, monthOf } from '@/utils/period'
import { dubaiToday, formatAED, formatDate } from '@/utils/format'

/** Central alert summary (same feed as the header bell and the Notifications page, so the numbers always agree). */
function AlertsWidget() {
  const summary = useAlertSummary()
  const s = summary.data
  return (
    <SectionCard
      title="Alerts"
      description="From the Notifications centre"
      actions={
        <Button variant="outline" size="sm" asChild>
          <Link to="/notifications">View all notifications</Link>
        </Button>
      }
    >
      {summary.error ? (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Alert counts">
            <StatCard
              label="Total Active Alerts"
              isLoading={summary.isLoading}
              value={s && String(s.total_active)}
            />
            <StatCard
              label="Critical"
              isLoading={summary.isLoading}
              value={s && String(s.critical)}
            />
            <StatCard
              label="Warning"
              isLoading={summary.isLoading}
              value={s && String(s.warning)}
            />
            <StatCard
              label="Informational"
              isLoading={summary.isLoading}
              value={s && String(s.info)}
            />
          </div>
          {s && s.recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active alerts.</p>
          ) : null}
          {s && s.recent.length > 0 ? (
            <ul className="space-y-2" aria-label="Recent alerts">
              {s.recent.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <SeverityBadge severity={a.severity} />
                  <Link to={a.href} className="text-primary underline-offset-4 hover:underline">
                    {a.type_label}
                  </Link>
                  <span className="text-muted-foreground">
                    {a.branch_name ? `${a.branch_name} · ` : ''}
                    {a.due_date ? `Due ${formatDate(a.due_date)}` : a.detail}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </SectionCard>
  )
}

function BalanceCards({ b, loading }: { b?: OwnerDashboardData['balances']; loading: boolean }) {
  if (b && b.status !== 'ok') {
    return (
      <p className="flex items-start gap-2 text-sm text-muted-foreground" role="status">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        {b.status === 'not_configured'
          ? 'Not configured: balances need the opening balances, which have not been saved yet.'
          : `Balances start from ${b.reporting_start ? formatDate(b.reporting_start) : 'the reporting start date'}; this period is earlier.`}
      </p>
    )
  }
  const items: [string, string | null | undefined][] = [
    ['Cash in Hand', b?.cash_in_hand],
    ['ENBD', b?.enbd],
    ['ADCB', b?.adcb],
    ['POS Pending', b?.pos_pending],
  ]
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(([label, v]) => (
        <StatCard
          key={label}
          label={label}
          isLoading={loading}
          value={v ? formatAED(v) : undefined}
        />
      ))}
    </div>
  )
}

export function OwnerDashboard() {
  const [params, setParams] = useSearchParams()
  const today = dubaiToday()
  const mode = params.get('view') === 'month' ? 'month' : 'day'
  const rawDate = params.get('date')
  const date = rawDate && /^\d{4}-\d{2}-\d{2}$/.test(rawDate) && rawDate <= today ? rawDate : today
  const rawMonth = params.get('month')
  const month =
    rawMonth && /^\d{4}-\d{2}$/.test(rawMonth) && rawMonth <= monthOf(today)
      ? rawMonth
      : monthOf(today)

  const set = (next: Record<string, string>) =>
    setParams({ view: mode, date, month, ...next }, { replace: true })
  const q = useOwnerDashboard(mode === 'day' ? { mode, date } : { mode, month })
  const d = q.data
  const k = d?.kpis
  const loading = q.isLoading
  const maxSales = Math.max(1, ...(d?.branches.map((b) => Number(b.total_sales)) ?? [0]))

  const period =
    mode === 'day' ? (
      <div className="flex flex-wrap items-end gap-2">
        <Button variant="outline" onClick={() => set({ date: addDays(date, -1) })}>
          <ChevronLeft aria-hidden /> Previous
        </Button>
        <FormDatePicker
          label="Date"
          value={date}
          max={today}
          onChange={(e) => e.target.value && set({ date: e.target.value })}
        />
        <Button
          variant="outline"
          disabled={date >= today}
          onClick={() => set({ date: addDays(date, 1) })}
        >
          Next <ChevronRight aria-hidden />
        </Button>
        <Button variant="secondary" onClick={() => set({ date: today })}>
          Today
        </Button>
      </div>
    ) : (
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => set({ month: addMonths(month, -1) })}>
          <ChevronLeft aria-hidden /> Previous Month
        </Button>
        <span className="min-w-36 text-center font-medium" aria-live="polite">
          {formatMonth(month)}
        </span>
        <Button
          variant="outline"
          disabled={month >= monthOf(today)}
          onClick={() => set({ month: addMonths(month, 1) })}
        >
          Next Month <ChevronRight aria-hidden />
        </Button>
        <Button variant="secondary" onClick={() => set({ month: monthOf(today) })}>
          This Month
        </Button>
      </div>
    )

  return (
    <PageContainer
      title="Dashboard"
      description="Overview of all branches, from submitted daily reports."
    >
      <SectionCard title="Period">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="inline-flex rounded-md border p-0.5" role="group" aria-label="View">
            {(['day', 'month'] as const).map((m) => (
              <Button
                key={m}
                size="sm"
                variant={mode === m ? 'default' : 'ghost'}
                aria-pressed={mode === m}
                onClick={() => set({ view: m })}
              >
                {m === 'day' ? 'Daily' : 'Monthly'}
              </Button>
            ))}
          </div>
          {period}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          The dashboard always covers all branches. Use Branch &amp; Date View for a single branch.
        </p>
      </SectionCard>

      {q.error ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="kpis">
            <StatCard
              label="Total Sales"
              isLoading={loading}
              value={k && formatAED(k.total_sales)}
            />
            <StatCard
              label="Total Received"
              isLoading={loading}
              value={k && formatAED(k.total_received)}
              description={k ? `Not yet received ${formatAED(k.not_yet_received)}` : undefined}
            />
            <StatCard
              label="Shop Expenses (excl. savings)"
              isLoading={loading}
              value={k && formatAED(k.shop_expenses_excl_savings)}
            />
            <StatCard
              label="Head Office Expenses (excl. savings)"
              isLoading={loading}
              value={k && formatAED(k.head_office_expenses_excl_savings)}
            />
            <StatCard
              label="Total Savings"
              isLoading={loading}
              value={k && formatAED(k.total_savings)}
            />
            <StatCard
              label="Sales Minus Expenses"
              isLoading={loading}
              value={k && formatAED(k.sales_minus_expenses)}
            />
            <StatCard label="Total Orders" isLoading={loading} value={k?.total_orders} />
            <StatCard
              label="Cash + Bank Balance"
              isLoading={loading}
              value={k?.cash_bank_balance ? formatAED(k.cash_bank_balance) : undefined}
              description={d && d.balances.status !== 'ok' ? 'Not configured' : undefined}
            />
          </div>

          <SectionCard
            title="Cash & bank summary"
            description={
              d?.balances.balance_date ? `As of ${formatDate(d.balances.balance_date)}` : undefined
            }
          >
            <BalanceCards b={d?.balances} loading={loading} />
          </SectionCard>

          <AlertsWidget />

          <SectionCard title="Needs attention">
            <div className="space-y-4">
              {d ? <MissingPanel missing={d.missing} /> : null}
              {d && d.alerts.filter((a) => a.key !== 'missing_reports').length > 0 ? (
                <ul className="space-y-2" aria-label="Other alerts">
                  {d.alerts
                    .filter((a) => a.key !== 'missing_reports')
                    .map((a) => (
                      <li key={a.key} className="flex flex-wrap items-center gap-2 text-sm">
                        <AlertTriangle className="size-4 text-warning" aria-hidden />
                        {a.href ? (
                          <Link
                            to={a.href}
                            className="text-primary underline-offset-4 hover:underline"
                          >
                            {a.title}
                          </Link>
                        ) : (
                          <span>{a.title}</span>
                        )}
                        <StatusBadge
                          status={
                            a.severity === 'danger'
                              ? 'danger'
                              : a.severity === 'info'
                                ? 'info'
                                : 'warning'
                          }
                        >
                          {a.key === 'suppliers_owed' && a.detail
                            ? formatAED(a.detail)
                            : String(a.count)}
                        </StatusBadge>
                      </li>
                    ))}
                </ul>
              ) : null}
            </div>
          </SectionCard>

          <SectionCard title="Sales by branch">
            {d && d.branches.every((b) => Number(b.total_sales) === 0) ? (
              <p className="text-sm text-muted-foreground">No sales recorded for this period.</p>
            ) : (
              <ul className="space-y-2" aria-label="Sales by branch">
                {(d?.branches ?? []).map((b) => (
                  <li
                    key={b.branch_id}
                    className="grid grid-cols-[7rem_1fr_auto] items-center gap-3 text-sm"
                  >
                    <span className="truncate">{b.branch_name}</span>
                    <span className="h-3 overflow-hidden rounded bg-secondary" aria-hidden>
                      <span
                        className="block h-full rounded bg-teal"
                        style={{ width: `${(Number(b.total_sales) / maxSales) * 100}%` }}
                      />
                    </span>
                    <span className="tabular">{formatAED(b.total_sales)}</span>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          {d?.days ? (
            <SectionCard title="Day by day">
              <DataTable
                caption="Day by day totals"
                rows={d.days}
                getRowId={(r) => r.date}
                columns={[
                  {
                    key: 'date',
                    header: 'Date',
                    cell: (r) => formatDate(r.date),
                    className: 'whitespace-nowrap',
                  },
                  { key: 'rep', header: 'Reports', align: 'right', cell: (r) => r.report_count },
                  {
                    key: 'miss',
                    header: 'Missing',
                    align: 'right',
                    cell: (r) => (r.missing_count === null ? '—' : r.missing_count),
                  },
                  {
                    key: 'sales',
                    header: 'Total Sales',
                    align: 'right',
                    cell: (r) => formatAED(r.total_sales),
                  },
                  {
                    key: 'rec',
                    header: 'Received',
                    align: 'right',
                    cell: (r) => formatAED(r.total_received),
                  },
                  {
                    key: 'exp',
                    header: 'Shop Exp.',
                    align: 'right',
                    cell: (r) => formatAED(r.shop_expenses_excl_savings),
                  },
                  {
                    key: 'ho',
                    header: 'Head Office',
                    align: 'right',
                    cell: (r) => formatAED(r.head_office_expenses_excl_savings),
                  },
                  {
                    key: 'sav',
                    header: 'Savings',
                    align: 'right',
                    cell: (r) => formatAED(r.total_savings),
                  },
                  {
                    key: 'net',
                    header: 'Sales − Expenses',
                    align: 'right',
                    cell: (r) => formatAED(r.sales_minus_expenses),
                  },
                ]}
              />
            </SectionCard>
          ) : null}

          <SectionCard title="Branch-wise summary">
            <DataTable
              caption="Branch-wise summary"
              rows={d?.branches}
              isLoading={loading}
              getRowId={(r) => r.branch_id}
              columns={[
                {
                  key: 'b',
                  header: 'Branch',
                  cell: (r) => r.branch_name,
                  className: 'whitespace-nowrap',
                },
                { key: 'rep', header: 'Reports', align: 'right', cell: (r) => r.report_count },
                {
                  key: 'miss',
                  header: 'Missing',
                  align: 'right',
                  cell: (r) => (r.missing_count === null ? '—' : r.missing_count),
                },
                {
                  key: 'sales',
                  header: 'Total Sales',
                  align: 'right',
                  cell: (r) => formatAED(r.total_sales),
                },
                { key: 'ord', header: 'Orders', align: 'right', cell: (r) => r.total_orders },
                {
                  key: 'rec',
                  header: 'Received',
                  align: 'right',
                  cell: (r) => formatAED(r.total_received),
                },
                {
                  key: 'nyr',
                  header: 'Not yet received',
                  align: 'right',
                  cell: (r) => formatAED(r.not_yet_received),
                },
                {
                  key: 'exp',
                  header: 'Shop Exp. (excl. savings)',
                  align: 'right',
                  cell: (r) => formatAED(r.shop_expenses_excl_savings),
                },
                {
                  key: 'sav',
                  header: 'Shop Savings',
                  align: 'right',
                  cell: (r) => formatAED(r.shop_savings),
                },
                {
                  key: 'ho',
                  header: 'Head Office (excl. savings)',
                  align: 'right',
                  cell: (r) => formatAED(r.head_office_excl_savings),
                },
              ]}
            />
            {d && Number(d.unallocated_head_office_excl_savings) !== 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">
                Head office spending tagged to all branches (
                {formatAED(d.unallocated_head_office_excl_savings)}) is in the totals above but not
                in any single branch row.
              </p>
            ) : null}
          </SectionCard>
        </>
      )}
    </PageContainer>
  )
}
