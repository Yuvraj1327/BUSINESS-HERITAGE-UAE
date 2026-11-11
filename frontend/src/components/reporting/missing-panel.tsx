import { CheckCircle2, Info } from 'lucide-react'
import { StatusBadge } from '@/components/common/status-badge'
import type { MissingReports } from '@/schemas/dashboard'
import { formatDate } from '@/utils/format'

/**
 * Missing daily reports. Before the reporting start date is configured (opening balances saved) nothing is
 * counted, and the panel says so instead of showing a misleading "0 missing".
 */
export function MissingPanel({
  missing,
  showBranch = true,
}: {
  missing: MissingReports
  showBranch?: boolean
}) {
  if (missing.status === 'not_configured') {
    return (
      <p className="flex items-start gap-2 text-sm text-muted-foreground" role="status">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        Reporting start date not configured yet. Missing reports are counted once the opening
        balances are saved.
      </p>
    )
  }
  if (missing.status === 'before_start') {
    return (
      <p className="flex items-start gap-2 text-sm text-muted-foreground" role="status">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        These dates are before reporting started
        {missing.reporting_start ? ` (${formatDate(missing.reporting_start)})` : ''}, so no reports
        are expected.
      </p>
    )
  }
  if (missing.expected === 0) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        No reports are due for this period yet.
      </p>
    )
  }
  if (missing.missing_count === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-success" role="status">
        <CheckCircle2 className="size-4" aria-hidden />
        All {missing.expected} expected reports are in.
      </p>
    )
  }
  return (
    <div className="space-y-3" role="status">
      <p className="text-sm">
        <span className="font-semibold">{missing.missing_count}</span> of {missing.expected}{' '}
        expected reports are missing
        {missing.date_from && missing.date_to
          ? ` (${formatDate(missing.date_from)} – ${formatDate(missing.date_to)})`
          : ''}
        .
      </p>
      <ul className="space-y-2">
        {missing.branches.map((b) => (
          <li key={b.branch_id} className="flex flex-wrap items-start gap-x-3 gap-y-1 text-sm">
            {showBranch ? <span className="min-w-28 font-medium">{b.branch_name}</span> : null}
            <StatusBadge status="warning">{`${b.missing_count} missing`}</StatusBadge>
            <span className="text-muted-foreground">
              {b.dates.length > 8
                ? `${b.dates.slice(0, 8).map(formatDate).join(', ')} and ${b.dates.length - 8} more`
                : b.dates.map(formatDate).join(', ')}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
