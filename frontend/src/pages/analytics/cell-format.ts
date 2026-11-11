import type { ReportColumn } from '@/schemas/analytics'
import { formatAED, formatDate } from '@/utils/format'

export function cellText(col: ReportColumn, v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  switch (col.kind) {
    case 'money':
      return formatAED(String(v))
    case 'int':
      return new Intl.NumberFormat('en-AE').format(Number(v))
    case 'pct':
      return `${String(v)}%`
    case 'date':
      return formatDate(String(v))
    case 'datetime': {
      const d = new Date(String(v))
      return Number.isNaN(d.getTime())
        ? String(v)
        : new Intl.DateTimeFormat('en-GB', {
            dateStyle: 'medium',
            timeStyle: 'short',
            timeZone: 'Asia/Dubai',
          }).format(d)
    }
    default:
      return String(v)
  }
}

export const summaryText = (kind: ReportColumn['kind'], v: unknown) =>
  cellText({ key: '', label: '', kind }, v)
