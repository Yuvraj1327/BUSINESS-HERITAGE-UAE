import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, Info, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '@/auth/use-auth'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { AuthLayout } from '@/layouts/AuthLayout'
import { getRememberSession } from '@/lib/auth-storage'
import { describeAuthError } from '@/lib/auth-errors'
import { loginSchema, type LoginValues } from '@/schemas/auth'
import { signInWithPassword } from '@/services/auth.service'

export function LoginPage() {
  const { sessionEnded } = useAuth()
  const passwordUpdated = (useLocation().state as { passwordUpdated?: boolean } | null)
    ?.passwordUpdated
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '', remember: getRememberSession() },
  })

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await signInWithPassword(values.email, values.password, values.remember)
      // Success: the auth listener updates the session and GuestRoute redirects into the app.
    } catch (err) {
      setFormError(describeAuthError(err).message)
    }
  })

  return (
    <AuthLayout
      title="Sign in"
      description="Use the account provided by your administrator."
      footer={
        <Link to="/forgot-password" className="underline underline-offset-4 hover:text-white">
          Forgot your password?
        </Link>
      }
    >
      {passwordUpdated ? (
        <p
          role="status"
          className="mb-4 flex gap-2 rounded-md bg-secondary p-3 text-sm text-secondary-foreground"
        >
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          Your password has been updated. Sign in with the new password.
        </p>
      ) : null}
      {sessionEnded ? (
        <p
          role="status"
          className="mb-4 flex gap-2 rounded-md bg-secondary p-3 text-sm text-secondary-foreground"
        >
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          Your session has ended. Please sign in again.
        </p>
      ) : null}
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
        <FormField label="Email" error={errors.email}>
          <Input
            type="email"
            autoComplete="username"
            inputMode="email"
            autoFocus
            {...register('email')}
          />
        </FormField>
        <FormField label="Password" error={errors.password}>
          <PasswordInput autoComplete="current-password" {...register('password')} />
        </FormField>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-[var(--primary)]"
            {...register('remember')}
          />
          Keep me signed in on this device
        </label>
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {isSubmitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </AuthLayout>
  )
}
