import { StatusBadge, type Status } from '@/components/common/status-badge'
import type { AlertSeverity, AlertStatus } from '@/schemas/alerts'

const SEV: Record<AlertSeverity, { tone: Status; label: string }> = {
  critical: { tone: 'danger', label: 'Critical' },
  warning: { tone: 'warning', label: 'Warning' },
  info: { tone: 'info', label: 'Informational' },
}
export const SeverityBadge = ({ severity }: { severity: AlertSeverity }) => (
  <StatusBadge status={SEV[severity].tone}>{SEV[severity].label}</StatusBadge>
)

const ST: Record<AlertStatus, { tone: Status; label: string }> = {
  unread: { tone: 'info', label: 'Unread' },
  read: { tone: 'neutral', label: 'Read' },
  acknowledged: { tone: 'success', label: 'Acknowledged' },
  resolved: { tone: 'success', label: 'Resolved' },
}
export const AlertStateBadge = ({ status }: { status: AlertStatus }) => (
  <StatusBadge status={ST[status].tone}>{ST[status].label}</StatusBadge>
)
