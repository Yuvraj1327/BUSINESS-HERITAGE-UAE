/** Date helpers on YYYY-MM-DD strings (UTC maths, so the browser time zone never shifts a business date). */
function parse(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`)
}
function fmt(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export function addDays(iso: string, days: number): string {
  const d = parse(iso)
  d.setUTCDate(d.getUTCDate() + days)
  return fmt(d)
}

/** 'YYYY-MM' of a date. */
export function monthOf(iso: string): string {
  return iso.slice(0, 7)
}

export function addMonths(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number) as [number, number]
  const d = new Date(Date.UTC(y, m - 1 + delta, 1))
  return fmt(d).slice(0, 7)
}

export function formatMonth(month: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parse(`${month}-01`))
}

export type QuickRange = 'today' | 'yesterday' | 'last7' | 'last14'

export const QUICK_RANGES: { key: QuickRange; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'last7', label: 'Last 7 days' },
  { key: 'last14', label: 'Last 14 days' },
]

/** Inclusive range ending today (or yesterday) in Dubai. `today` comes from dubaiToday(). */
export function quickRange(key: QuickRange, today: string): { from: string; to: string } {
  switch (key) {
    case 'today':
      return { from: today, to: today }
    case 'yesterday': {
      const y = addDays(today, -1)
      return { from: y, to: y }
    }
    case 'last7':
      return { from: addDays(today, -6), to: today }
    case 'last14':
      return { from: addDays(today, -13), to: today }
  }
}
