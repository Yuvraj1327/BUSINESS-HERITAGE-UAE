import { Info } from 'lucide-react'
import { toast } from 'sonner'
import { usePermissions } from '@/auth/use-permissions'
import { useAuth } from '@/auth/use-auth'
import { SectionCard } from '@/components/common/section-card'
import { Switch } from '@/components/ui/switch'
import { useSavePreferences } from '@/hooks/use-settings'
import { DEFAULT_PREFERENCES, type Preferences } from '@/schemas/preferences'

const ROWS = [
  {
    key: 'critical',
    label: 'Critical alerts',
    hint: 'Overdue and expired items that need action now.',
  },
  { key: 'warning', label: 'Warnings', hint: 'Items approaching a due or expiry date.' },
  { key: 'info', label: 'Information', hint: 'Low-priority updates.' },
] as const

/** In-app only: nothing is emailed or pushed. These choices control what the header bell shows. */
export function NotificationSettingsPage() {
  const { profile } = useAuth()
  const { can } = usePermissions()
  const save = useSavePreferences()
  const prefs = profile?.preferences ?? DEFAULT_PREFERENCES
  const hasAlerts = can('alerts', 'read')

  function toggle(key: keyof Preferences['notifications'], value: boolean) {
    save.mutate(
      { ...prefs, notifications: { ...prefs.notifications, [key]: value } },
      { onSuccess: () => toast.success('Notification preferences saved') },
    )
  }

  return (
    <SectionCard
      title="In-app notifications"
      description="Choose which alert levels appear in the notification bell. Nothing is sent by email or SMS."
    >
      {hasAlerts ? (
        <ul className="divide-y">
          {ROWS.map((r) => (
            <li key={r.key} className="flex items-center justify-between gap-4 py-3">
              <div id={`n-${r.key}`}>
                <p className="font-medium">{r.label}</p>
                <p className="text-sm text-muted-foreground">{r.hint}</p>
              </div>
              <Switch
                aria-labelledby={`n-${r.key}`}
                checked={prefs.notifications[r.key]}
                onCheckedChange={(v) => toggle(r.key, v)}
                disabled={save.isPending}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          Alert notifications (tasks, licences, cheques, compliance) are generated for Owners. Your
          account has no notification categories to configure.
        </p>
      )}
      {hasAlerts ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Muted levels are hidden from the bell only. The Notifications page still lists every
          active alert, so nothing is lost.
        </p>
      ) : null}
    </SectionCard>
  )
}
