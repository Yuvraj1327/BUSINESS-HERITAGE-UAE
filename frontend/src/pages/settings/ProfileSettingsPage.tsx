import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, Trash2, Upload, Users } from 'lucide-react'
import { useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Can } from '@/auth/permission-guards'
import { useAuth } from '@/auth/use-auth'
import { SectionCard } from '@/components/common/section-card'
import { FormActions } from '@/components/forms/form-actions'
import { FormInput } from '@/components/forms/form-input'
import { UserAvatar } from '@/components/layout/user-avatar'
import { Button } from '@/components/ui/button'
import { useAvatarUrl, useUpdateProfile } from '@/hooks/use-settings'
import { getErrorMessage } from '@/lib/errors'
import { AVATAR_MAX_BYTES, profileFormSchema, type ProfileFormValues } from '@/schemas/settings'
import { AvatarError, removeAvatarObject, uploadAvatar } from '@/services/settings.service'
import { roleLabel } from '@/utils/user'

function ReadOnly({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="text-sm break-words">{value}</dd>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

function PhotoCard() {
  const { profile, user } = useAuth()
  const update = useUpdateProfile()
  const url = useAvatarUrl(profile?.avatar_path)
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  if (!profile || !user) return null

  async function onFile(file: File | undefined) {
    if (!file || !profile) return
    setBusy(true)
    let path: string | null = null
    try {
      path = await uploadAvatar(profile.user_id, file)
      await update.mutateAsync({ avatar_path: path })
      void removeAvatarObject(profile.avatar_path) // the previous photo is no longer referenced
      toast.success('Profile photo updated')
    } catch (err) {
      if (path) void removeAvatarObject(path) // do not leave an unreferenced upload behind
      if (err instanceof AvatarError) toast.error(err.message)
      else if (path) toast.error(getErrorMessage(err))
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  async function onRemove() {
    if (!profile?.avatar_path) return
    setBusy(true)
    try {
      const old = profile.avatar_path
      await update.mutateAsync({ avatar_path: null })
      void removeAvatarObject(old)
      toast.success('Profile photo removed')
    } catch {
      /* the global handler already showed the error */
    } finally {
      setBusy(false)
    }
  }

  return (
    <SectionCard title="Profile photo" description="JPG, PNG or WebP, up to 2 MB.">
      <div className="flex flex-wrap items-center gap-4">
        <UserAvatar name={profile.full_name} src={url} className="size-20 text-xl" />
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            aria-label="Choose a profile photo"
            data-testid="avatar-input"
            onChange={(e) => void onFile(e.target.files?.[0])}
            disabled={busy}
          />
          <Button
            type="button"
            variant="outline"
            className="h-11 sm:h-9"
            disabled={busy}
            onClick={() => input.current?.click()}
          >
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Upload aria-hidden />}
            {profile.avatar_path ? 'Change photo' : 'Upload photo'}
          </Button>
          {profile.avatar_path ? (
            <Button
              type="button"
              variant="ghost"
              className="h-11 sm:h-9"
              disabled={busy}
              onClick={() => void onRemove()}
            >
              <Trash2 aria-hidden /> Remove
            </Button>
          ) : null}
        </div>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Your photo is private: it is visible to you and to the Owner only. Maximum{' '}
        {AVATAR_MAX_BYTES / 1024 / 1024} MB.
      </p>
    </SectionCard>
  )
}

export function ProfileSettingsPage() {
  const { profile, user } = useAuth()
  const update = useUpdateProfile()
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: { full_name: profile?.full_name ?? '', phone: profile?.phone ?? '' },
  })
  if (!profile) return null

  const onSubmit = handleSubmit(async (values) => {
    const next = await update.mutateAsync({
      full_name: values.full_name,
      phone: values.phone === '' ? null : values.phone,
    })
    reset({ full_name: next.full_name, phone: next.phone ?? '' })
    toast.success('Profile saved')
  })

  return (
    <>
      <PhotoCard />
      <SectionCard
        title="Personal details"
        description="You can edit your own name and phone number."
      >
        <form onSubmit={(e) => void onSubmit(e)} noValidate className="grid max-w-xl gap-4">
          <FormInput
            label="Full name"
            required
            autoComplete="name"
            error={errors.full_name}
            {...register('full_name')}
          />
          <FormInput
            label="Phone number"
            type="tel"
            autoComplete="tel"
            placeholder="+971 50 123 4567"
            error={errors.phone}
            {...register('phone')}
          />
          <FormActions
            submitLabel="Save changes"
            isSubmitting={update.isPending}
            disabled={!isDirty}
            onCancel={isDirty ? () => reset() : undefined}
            cancelLabel="Discard"
          />
        </form>
      </SectionCard>
      <SectionCard
        title="Account"
        description="Set by your administrator. Change your email under Account & Security."
      >
        <dl className="grid gap-4 sm:grid-cols-3">
          <ReadOnly label="Email" value={user?.email ?? '—'} />
          <ReadOnly
            label="Role"
            value={roleLabel(profile.role)}
            hint="Only an Owner can change roles."
          />
          <ReadOnly
            label="Assigned branch"
            value={profile.branch_name ?? 'All branches'}
            hint="Only an Owner can change branch assignments."
          />
        </dl>
      </SectionCard>
      <Can module="user_management" action="read">
        <SectionCard
          title="User management"
          description="Owners manage other people's accounts here."
        >
          <Button asChild variant="outline" className="h-11 sm:h-9">
            <Link to="/users">
              <Users aria-hidden /> Manage users
            </Link>
          </Button>
        </SectionCard>
      </Can>
    </>
  )
}
