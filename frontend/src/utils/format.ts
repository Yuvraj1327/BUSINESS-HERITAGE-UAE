import { BUSINESS_TIMEZONE, CURRENCY } from '@/constants'
import type { DateFormatChoice } from '@/schemas/preferences'

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

/**
 * The signed-in user's display preferences (Settings > Preferences). Set once by the app shell. They change
 * ONLY how dates/times are shown: business dates ("today", report dates, cut-offs) are always Dubai time, and
 * every amount is AED.
 */
export interface DisplayPrefs {
  dateFormat: DateFormatChoice
  /** 'Asia/Dubai' (business), 'device', or an IANA zone. */
  timezone: string
}
const DEFAULT_DISPLAY: DisplayPrefs = { dateFormat: 'dd-mmm-yyyy', timezone: BUSINESS_TIMEZONE }
let display: DisplayPrefs = DEFAULT_DISPLAY
export function setDisplayPrefs(next: Partial<DisplayPrefs> | null) {
  display = {
    dateFormat: next?.dateFormat ?? DEFAULT_DISPLAY.dateFormat,
    timezone: next?.timezone ?? DEFAULT_DISPLAY.timezone,
  }
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function layoutDate(
  y: string,
  m: string,
  d: string,
  format: DateFormatChoice = display.dateFormat,
) {
  switch (format) {
    case 'dd/mm/yyyy':
      return `${d}/${m}/${y}`
    case 'mm/dd/yyyy':
      return `${m}/${d}/${y}`
    case 'yyyy-mm-dd':
      return `${y}-${m}-${d}`
    default:
      return `${d} ${MONTHS[Number(m) - 1] ?? m} ${y}`
  }
}

/** A calendar date (YYYY-MM-DD) in the user's chosen layout. No timezone shift: it is a business date. */
export function formatDate(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate)
  if (!m || Number.isNaN(new Date(`${isoDate.slice(0, 10)}T00:00:00Z`).getTime())) return '—'
  return layoutDate(m[1]!, m[2]!, m[3]!)
}

/** Date and time (e.g. "10 Nov 2026, 14:30") for an ISO timestamp, in the user's display timezone. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const timeZone = display.timezone === 'device' ? undefined : display.timezone
  const p = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone,
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
  const hour = p.hour === '24' ? '00' : p.hour
  return `${layoutDate(p.year!, p.month!, p.day!)}, ${hour}:${p.minute}`
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
