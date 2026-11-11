import { Monitor, Moon, Sun, type LucideIcon } from 'lucide-react'
import { useAuth } from '@/auth/use-auth'
import { SectionCard } from '@/components/common/section-card'
import { useSavePreferences } from '@/hooks/use-settings'
import { cn } from '@/lib/utils'
import { DEFAULT_PREFERENCES, type ThemeChoice } from '@/schemas/preferences'
import { applyTheme, readStoredTheme, storeTheme } from '@/theme/theme'
import { toast } from 'sonner'

const OPTIONS: { value: ThemeChoice; label: string; hint: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Light', hint: 'Bright surfaces', icon: Sun },
  { value: 'dark', label: 'Dark', hint: 'Easier on the eyes at night', icon: Moon },
  { value: 'system', label: 'System', hint: 'Follow this device', icon: Monitor },
]

export function AppearanceSettingsPage() {
  const { profile } = useAuth()
  const save = useSavePreferences()
  const current = profile?.preferences.theme ?? readStoredTheme()

  function choose(theme: ThemeChoice) {
    if (theme === current) return
    storeTheme(theme)
    applyTheme(theme) // instant; the saved copy follows
    save.mutate(
      { ...(profile?.preferences ?? DEFAULT_PREFERENCES), theme },
      {
        onSuccess: () => toast.success('Theme saved'),
        onError: () =>
          toast.error('Theme applied on this device, but could not be saved to your account.'),
      },
    )
  }

  return (
    <SectionCard
      title="Theme"
      description="Your choice is remembered on this device and saved to your account."
    >
      <div role="radiogroup" aria-label="Theme" className="grid gap-3 sm:grid-cols-3">
        {OPTIONS.map(({ value, label, hint, icon: Icon }) => {
          const selected = current === value
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => choose(value)}
              className={cn(
                'flex min-h-20 items-center gap-3 rounded-xl border p-4 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring',
                selected ? 'border-accent bg-secondary' : 'hover:bg-muted',
              )}
            >
              <Icon className="size-6 shrink-0 text-primary" aria-hidden />
              <span>
                <span className="block font-semibold">{label}</span>
                <span className="block text-xs text-muted-foreground">{hint}</span>
              </span>
            </button>
          )
        })}
      </div>
    </SectionCard>
  )
}
