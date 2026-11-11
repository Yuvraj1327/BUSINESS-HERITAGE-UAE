import type { AuditEntry } from '@/schemas/finance'

/** Today's date in Dubai as YYYY-MM-DD (used only to limit date pickers; the server decides). */
export const todayDubai = (): string =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dubai' }).format(new Date())

/** Preview only (the server decides): start + 12 months - 1 day, clamped to the month end. */
export function defaultEndDate(start: string): string {
  const [y, m, d] = start.split('-').map(Number) as [number, number, number]
  const last = new Date(Date.UTC(y + 1, m, 0)).getUTCDate()
  const end = new Date(Date.UTC(y + 1, m - 1, Math.min(d, last)))
  end.setUTCDate(end.getUTCDate() - 1)
  return end.toISOString().slice(0, 10)
}

export function dueText(days: number | null | undefined): string {
  if (days === null || days === undefined) return ''
  if (days < 0) return `${-days} day${days === -1 ? '' : 's'} overdue`
  if (days === 0) return 'Due today'
  return `Due in ${days} day${days === 1 ? '' : 's'}`
}

export function endText(days: number): string {
  if (days < 0) return `Ended ${-days} day${days === -1 ? '' : 's'} ago`
  if (days === 0) return 'Ends today'
  return `${days} day${days === 1 ? '' : 's'} left`
}

const HIDDEN = new Set([
  'updated_at',
  'updated_by',
  'created_at',
  'created_by',
  'id',
  'cleared_at',
  'bounced_at',
])
const LABEL: Record<string, string> = {
  branch_id: 'Branch',
  landlord: 'Landlord',
  unit: 'Rental unit',
  start_date: 'Start date',
  end_date: 'End date',
  annual_rent: 'Annual rent',
  status: 'Status',
  notes: 'Notes',
  cheque_no: 'Cheque number',
  cheque_date: 'Cheque date',
  amount: 'Amount',
  bank: 'Bank',
  cleared_on: 'Cleared on',
  bounced_on: 'Bounced on',
  cheque_count: 'Cheques',
  first_cheque_date: 'First cheque date',
  first_cheque_no: 'First cheque number',
}
const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))
/** "Status: Pending → Cleared" from an audit row; no raw JSON in the UI. */
export function describeChange(e: AuditEntry): string {
  if (e.action === 'INSERT') return 'Record created'
  const o = e.old_values ?? {}
  const n = e.new_values ?? {}
  const parts = Object.keys(n)
    .filter((k) => !HIDDEN.has(k) && JSON.stringify(o[k]) !== JSON.stringify(n[k]))
    .map((k) => `${LABEL[k] ?? k}: ${show(o[k])} → ${show(n[k])}`)
  return parts.join('; ') || 'No visible change'
}
