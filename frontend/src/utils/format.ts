import { BUSINESS_TIMEZONE, CURRENCY } from '@/constants'

export function formatAED(value: number | string, decimals = 2): string {
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '—'
  return new Intl.NumberFormat('en-AE', {
    style: 'currency',
    currency: CURRENCY,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(n)
}

/** Today's business date (YYYY-MM-DD) in Dubai, independent of the browser's time zone. */
export function dubaiToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIMEZONE }).format(now)
}

export function formatDate(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(d)
}

/** Date and time in Dubai (e.g. "10 Nov 2026, 14:30") for an ISO timestamp from the server. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: BUSINESS_TIMEZONE,
  }).format(d)
}

/** Split an ISO timestamp into the Dubai calendar date (YYYY-MM-DD) and clock time (HH:MM) for form fields. */
export function dubaiParts(iso: string | null | undefined): { date: string; time: string } {
  if (!iso) return { date: '', time: '' }
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return { date: '', time: '' }
  const p = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: BUSINESS_TIMEZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
      .formatToParts(d)
      .map((x) => [x.type, x.value]),
  )
  return {
    date: `${p.year}-${p.month}-${p.day}`,
    time: `${p.hour === '24' ? '00' : p.hour}:${p.minute}`,
  }
}
