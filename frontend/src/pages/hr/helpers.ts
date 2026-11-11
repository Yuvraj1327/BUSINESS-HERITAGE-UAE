import type { AuditEntry } from '@/schemas/finance'

export function daysText(days: number | null | undefined): string {
  if (days === null || days === undefined) return ''
  if (days < 0) return `${-days} day${days === -1 ? '' : 's'} overdue`
  if (days === 0) return 'Today'
  return `${days} day${days === 1 ? '' : 's'} left`
}

const HIDDEN = new Set(['updated_at', 'updated_by', 'created_at', 'created_by', 'id'])
const LABEL: Record<string, string> = {
  full_name: 'Name',
  branch_id: 'Branch',
  role_title: 'Role',
  monthly_salary: 'Salary',
  status: 'Status',
  leave_start: 'Leave start',
  visa_cancelled: 'Visa cancelled',
  visa_cancelled_date: 'Visa cancelled on',
  visa_expiry: 'Visa expiry',
  passport_expiry: 'Passport expiry',
  notes: 'Notes',
  archived_at: 'Archived',
  archive_reason: 'Archive reason',
  license_no: 'Licence no.',
  authority: 'Authority',
  expiry_date: 'Expiry',
  renewal_fee: 'Renewal fee',
}
const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))
/** "Salary: 1500.00 → 1800.00; Status: Active → Leave" from an audit row; no raw JSON in the UI. */
export function describeChange(e: AuditEntry): string {
  if (e.action === 'INSERT') return 'Record created'
  const o = e.old_values ?? {}
  const n = e.new_values ?? {}
  const parts = Object.keys(n)
    .filter((k) => !HIDDEN.has(k) && JSON.stringify(o[k]) !== JSON.stringify(n[k]))
    .map((k) => `${LABEL[k] ?? k}: ${show(o[k])} → ${show(n[k])}`)
  return parts.join('; ') || 'No visible change'
}

/** Preview only (the server decides): same date next year; 29 Feb becomes 28 Feb. */
export function previewRenewal(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number) as [number, number, number]
  const last = new Date(Date.UTC(y + 1, m, 0)).getUTCDate()
  const day = Math.min(d, last)
  return `${y + 1}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}
