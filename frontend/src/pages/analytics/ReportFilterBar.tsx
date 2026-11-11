import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormSelect } from '@/components/forms/form-select'
import { useBranchContext } from '@/components/layout/branch-context'
import { Button } from '@/components/ui/button'
import type { Period } from '@/services/analytics.service'
import { dubaiToday } from '@/utils/format'
import { RANGES, type RangeKey } from './ranges'

export interface FilterState {
  range: RangeKey
  from: string
  to: string
  period: Period
  branch: string
}

const PERIODS: { value: Period; label: string }[] = [
  { value: 'day', label: 'Daily' },
  { value: 'week', label: 'Weekly' },
  { value: 'month', label: 'Monthly' },
  { value: 'year', label: 'Yearly' },
]

interface Props {
  value: FilterState
  onRange: (key: RangeKey) => void
  onChange: (patch: Partial<FilterState>) => void
  showPeriod?: boolean
  showBranch?: boolean
}

/** The filters every report shares: quick ranges, custom dates, grouping and branch. */
export function ReportFilterBar({
  value,
  onRange,
  onChange,
  showPeriod = true,
  showBranch = true,
}: Props) {
  const { branches } = useBranchContext()
  const today = dubaiToday()
  return (
    <div
      className="space-y-3 rounded-xl border bg-card p-4 shadow-card"
      aria-label="Report filters"
    >
      <div className="flex flex-wrap gap-2" role="group" aria-label="Quick date ranges">
        {RANGES.map((r) => (
          <Button
            key={r.key}
            size="sm"
            variant={value.range === r.key ? 'default' : 'outline'}
            aria-pressed={value.range === r.key}
            onClick={() => onRange(r.key)}
          >
            {r.label}
          </Button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <FormDatePicker
          label="Start date"
          value={value.from}
          max={value.to || today}
          onChange={(e) => onChange({ range: 'custom', from: e.target.value })}
        />
        <FormDatePicker
          label="End date"
          value={value.to}
          min={value.from}
          max={today}
          onChange={(e) => onChange({ range: 'custom', to: e.target.value })}
        />
        {showPeriod ? (
          <FormSelect
            label="Group by"
            value={value.period}
            options={PERIODS}
            onValueChange={(v) => onChange({ period: v as Period })}
          />
        ) : null}
        {showBranch ? (
          <FormSelect
            label="Branch"
            value={value.branch}
            options={[
              { value: 'all', label: 'All Branches' },
              ...branches.map((b) => ({ value: b.id, label: b.name })),
            ]}
            onValueChange={(v) => onChange({ branch: v })}
          />
        ) : null}
      </div>
    </div>
  )
}
