import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/use-auth'
import { LoadingIndicator } from '@/components/common/loading-indicator'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { PasswordInput } from '@/components/ui/password-input'
import { AuthLayout } from '@/layouts/AuthLayout'
import { describeAuthError } from '@/lib/auth-errors'
import { newPasswordSchema, PASSWORD_MIN_LENGTH, type NewPasswordValues } from '@/schemas/auth'
import { updatePassword } from '@/services/auth.service'
import { ConfigMissingPage } from '@/pages/auth/ConfigMissingPage'

export function ResetPasswordPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<NewPasswordValues>({
    resolver: zodResolver(newPasswordSchema),
    defaultValues: { password: '', confirmPassword: '' },
  })

  if (auth.status === 'unconfigured') return <ConfigMissingPage />
  if (auth.status === 'loading') {
    return (
      <div className="grid min-h-dvh place-items-center bg-sidebar text-white">
        <LoadingIndicator label="Checking your reset link…" className="text-white" />
      </div>
    )
  }

  // A valid reset link signs the user in with a recovery session. Without one the link is invalid/expired/used.
  if (auth.status === 'unauthenticated') {
    return (
      <AuthLayout
        title="Reset link not valid"
        description="This password reset link is invalid, has expired or was already used."
        footer={
          <Link to="/login" className="underline underline-offset-4 hover:text-white">
            Back to sign in
          </Link>
        }
      >
        <Button asChild className="w-full">
          <Link to="/forgot-password">Request a new link</Link>
        </Button>
      </AuthLayout>
    )
  }

  const onSubmit = handleSubmit(async ({ password }) => {
    setFormError(null)
    try {
      await updatePassword(password)
    } catch (err) {
      setFormError(describeAuthError(err).message)
      return
    }
    // End the recovery session so the user signs in with the new password.
    await auth.signOut()
    void navigate('/login', { replace: true, state: { passwordUpdated: true } })
  })

  return (
    <AuthLayout title="Choose a new password" description="Enter a new password for your account.">
      <form onSubmit={(e) => void onSubmit(e)} noValidate className="grid gap-4">
        {formError ? (
          <p
            role="alert"
            className="flex gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {formError}
          </p>
        ) : null}
        <FormField
          label="New password"
          error={errors.password}
          description={`At least ${PASSWORD_MIN_LENGTH} characters, with letters and numbers.`}
        >
          <PasswordInput autoComplete="new-password" autoFocus {...register('password')} />
        </FormField>
        <FormField label="Confirm new password" error={errors.confirmPassword}>
          <PasswordInput autoComplete="new-password" {...register('confirmPassword')} />
        </FormField>
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {isSubmitting ? 'Saving…' : 'Update password'}
        </Button>
      </form>
    </AuthLayout>
  )
}
