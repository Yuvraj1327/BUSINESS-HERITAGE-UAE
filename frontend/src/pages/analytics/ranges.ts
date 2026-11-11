import { addDays } from '@/utils/period'

export type RangeKey =
  'today' | 'yesterday' | 'last7' | 'last30' | 'this_month' | 'last_month' | 'this_year' | 'custom'

export const RANGES: { key: RangeKey; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'last7', label: 'Last 7 Days' },
  { key: 'last30', label: 'Last 30 Days' },
  { key: 'this_month', label: 'This Month' },
  { key: 'last_month', label: 'Last Month' },
  { key: 'this_year', label: 'This Year' },
  { key: 'custom', label: 'Custom Range' },
]

/** Inclusive Dubai-date range for a quick filter. `today` is the Dubai business date (YYYY-MM-DD). */
export function rangeFor(
  key: Exclude<RangeKey, 'custom'>,
  today: string,
): { from: string; to: string } {
  const month = today.slice(0, 7)
  switch (key) {
    case 'today':
      return { from: today, to: today }
    case 'yesterday': {
      const y = addDays(today, -1)
      return { from: y, to: y }
    }
    case 'last7':
      return { from: addDays(today, -6), to: today }
    case 'last30':
      return { from: addDays(today, -29), to: today }
    case 'this_month':
      return { from: `${month}-01`, to: today }
    case 'last_month': {
      const firstThis = `${month}-01`
      const lastPrev = addDays(firstThis, -1)
      return { from: `${lastPrev.slice(0, 7)}-01`, to: lastPrev }
    }
    case 'this_year':
      return { from: `${today.slice(0, 4)}-01-01`, to: today }
  }
}
