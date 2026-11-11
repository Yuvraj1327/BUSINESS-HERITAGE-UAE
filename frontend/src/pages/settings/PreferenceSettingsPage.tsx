import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { useAuth } from '@/auth/use-auth'
import { SectionCard } from '@/components/common/section-card'
import { FormActions } from '@/components/forms/form-actions'
import { FormSelect } from '@/components/forms/form-select'
import { BUSINESS_TIMEZONE, CURRENCY } from '@/constants'
import { useSavePreferences } from '@/hooks/use-settings'
import {
  DATE_FORMATS,
  DEFAULT_PREFERENCES,
  DISPLAY_TIMEZONES,
  type Preferences,
} from '@/schemas/preferences'

type Values = Pick<Preferences, 'language' | 'date_format' | 'timezone'>

export function PreferenceSettingsPage() {
  const { profile } = useAuth()
  const save = useSavePreferences()
  const prefs = profile?.preferences ?? DEFAULT_PREFERENCES
  const { control, handleSubmit, reset, formState } = useForm<Values>({
    defaultValues: {
      language: prefs.language,
      date_format: prefs.date_format,
      timezone: prefs.timezone,
    },
  })
  const onSubmit = handleSubmit(async (v) => {
    const next = await save.mutateAsync({ ...prefs, ...v })
    reset({
      language: next.preferences.language,
      date_format: next.preferences.date_format,
      timezone: next.preferences.timezone,
    })
    toast.success('Preferences saved')
  })

  return (
    <>
      <SectionCard
        title="Display preferences"
        description="These change how dates and times are shown to you only."
      >
        <form onSubmit={(e) => void onSubmit(e)} className="grid max-w-xl gap-4">
          <Controller
            control={control}
            name="language"
            render={({ field }) => (
              <FormSelect
                label="Language"
                value={field.value}
                onValueChange={field.onChange}
                options={[{ value: 'en', label: 'English' }]}
                description="Arabic is not available yet: the screens are not translated."
              />
            )}
          />
          <Controller
            control={control}
            name="date_format"
            render={({ field }) => (
              <FormSelect
                label="Date format"
                value={field.value}
                onValueChange={field.onChange}
                options={DATE_FORMATS.map((f) => ({ value: f.value, label: f.label }))}
              />
            )}
          />
          <Controller
            control={control}
            name="timezone"
            render={({ field }) => (
              <FormSelect
                label="Time zone for timestamps"
                value={field.value}
                onValueChange={field.onChange}
                options={DISPLAY_TIMEZONES.map((t) => ({ value: t.value, label: t.label }))}
                description="Only the time shown on records changes. Reporting dates and cut-offs always use UAE time."
              />
            )}
          />
          <FormActions
            submitLabel="Save preferences"
            isSubmitting={save.isPending}
            disabled={!formState.isDirty}
          />
        </form>
      </SectionCard>
      <SectionCard
        title="Business rules"
        description="Fixed for the whole company so every branch reports the same way."
      >
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium text-muted-foreground">Currency</dt>
            <dd className="text-sm">{CURRENCY} (UAE dirham), all amounts</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted-foreground">Business time zone</dt>
            <dd className="text-sm">
              {BUSINESS_TIMEZONE} (UAE, UTC+4), used for “today” and daily reports
            </dd>
          </div>
        </dl>
      </SectionCard>
    </>
  )
}
