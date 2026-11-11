import { zodResolver } from '@hookform/resolvers/zod'
import { Laptop, LogOut, MailCheck } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { useAuth } from '@/auth/use-auth'
import { SectionCard } from '@/components/common/section-card'
import { FormActions } from '@/components/forms/form-actions'
import { FormField } from '@/components/common/form-field'
import { FormInput } from '@/components/forms/form-input'
import { SignOutDialog } from '@/components/layout/sign-out-dialog'
import { Button } from '@/components/ui/button'
import { PasswordInput } from '@/components/ui/password-input'
import { describeAuthError } from '@/lib/auth-errors'
import {
  changeEmailSchema,
  changePasswordSchema,
  type ChangeEmailValues,
  type ChangePasswordValues,
} from '@/schemas/settings'
import {
  changePassword,
  requestEmailChange,
  signOutOtherDevices,
} from '@/services/settings.service'
import { describeDevice } from '@/utils/device'
import { formatDateTime } from '@/utils/format'

function PasswordCard() {
  const { user } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current: '', password: '', confirm: '' },
  })
  const onSubmit = handleSubmit(async ({ current, password }) => {
    setError(null)
    try {
      await changePassword(user?.email ?? '', current, password)
      reset()
      toast.success('Password changed')
    } catch (err) {
      setError(
        err instanceof Error && err.message.startsWith('Your current')
          ? err.message
          : describeAuthError(err).message,
      )
    }
  })
  return (
    <SectionCard
      title="Change password"
      description="Use at least 10 characters with upper case, lower case and a number."
    >
      <form onSubmit={(e) => void onSubmit(e)} noValidate className="grid max-w-xl gap-4">
        <FormField label="Current password" required error={errors.current}>
          <PasswordInput autoComplete="current-password" {...register('current')} />
        </FormField>
        <FormField label="New password" required error={errors.password}>
          <PasswordInput autoComplete="new-password" {...register('password')} />
        </FormField>
        <FormField label="Confirm new password" required error={errors.confirm}>
          <PasswordInput autoComplete="new-password" {...register('confirm')} />
        </FormField>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <FormActions submitLabel="Change password" isSubmitting={isSubmitting} />
      </form>
    </SectionCard>
  )
}

function EmailCard() {
  const { user } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [sentTo, setSentTo] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ChangeEmailValues>({
    resolver: zodResolver(changeEmailSchema),
    defaultValues: { email: '', current: '' },
  })
  const pending = sentTo ?? user?.new_email ?? null
  const onSubmit = handleSubmit(async ({ email, current }) => {
    setError(null)
    if (email.toLowerCase() === (user?.email ?? '').toLowerCase()) {
      setError('That is already your email address.')
      return
    }
    try {
      await requestEmailChange(user?.email ?? '', current, email)
      setSentTo(email)
      reset()
      toast.success('Confirmation email sent')
    } catch (err) {
      setError(
        err instanceof Error && err.message.startsWith('Your current')
          ? err.message
          : describeAuthError(err).message,
      )
    }
  })
  return (
    <SectionCard
      title="Change email"
      description="Your sign-in email only changes after you confirm it from the link we send."
    >
      <p className="mb-4 text-sm">
        Current email: <strong className="font-semibold">{user?.email ?? '—'}</strong>
      </p>
      {pending ? (
        <p
          role="status"
          className="mb-4 flex items-start gap-2 rounded-lg bg-secondary p-3 text-sm text-secondary-foreground"
        >
          <MailCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            Waiting for confirmation of <strong>{pending}</strong>. Open the link in the email{' '}
            Supabase sent (check both inboxes if asked). Until then you keep signing in with your
            current email.
          </span>
        </p>
      ) : null}
      <form onSubmit={(e) => void onSubmit(e)} noValidate className="grid max-w-xl gap-4">
        <FormInput
          label="New email address"
          type="email"
          required
          autoComplete="email"
          error={errors.email}
          {...register('email')}
        />
        <FormField label="Current password" required error={errors.current}>
          <PasswordInput autoComplete="current-password" {...register('current')} />
        </FormField>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <FormActions submitLabel="Send confirmation email" isSubmitting={isSubmitting} />
      </form>
    </SectionCard>
  )
}

function SessionCard() {
  const { session, user } = useAuth()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  async function others() {
    setBusy(true)
    try {
      await signOutOtherDevices()
      toast.success('Signed out of all other devices')
    } catch (err) {
      toast.error(describeAuthError(err).message)
    } finally {
      setBusy(false)
    }
  }
  const expires = session?.expires_at ? new Date(session.expires_at * 1000).toISOString() : null
  return (
    <SectionCard
      title="Sessions"
      description="Where you are signed in. Access tokens renew automatically while you use the app."
    >
      <div className="flex items-start gap-3 rounded-xl border p-3">
        <Laptop className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <dl className="grid min-w-0 flex-1 gap-1 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">This device</dt>
            <dd>{describeDevice(navigator.userAgent)} (current session)</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Last sign-in</dt>
            <dd>{formatDateTime(user?.last_sign_in_at)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Access token renews at</dt>
            <dd>{formatDateTime(expires)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Account created</dt>
            <dd>{formatDateTime(user?.created_at)}</dd>
          </div>
        </dl>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Other devices are not listed individually (the sign-in service does not expose them to the
        browser), but you can end all of them below.
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Button
          type="button"
          variant="outline"
          className="h-11 sm:h-9"
          disabled={busy}
          onClick={() => void others()}
        >
          Sign out other devices
        </Button>
        <Button
          type="button"
          variant="destructive"
          className="h-11 sm:h-9"
          onClick={() => setConfirmOpen(true)}
        >
          <LogOut aria-hidden /> Sign out
        </Button>
      </div>
      <SignOutDialog open={confirmOpen} onOpenChange={setConfirmOpen} />
    </SectionCard>
  )
}

export function SecuritySettingsPage() {
  return (
    <>
      <PasswordCard />
      <EmailCard />
      <SessionCard />
    </>
  )
}
