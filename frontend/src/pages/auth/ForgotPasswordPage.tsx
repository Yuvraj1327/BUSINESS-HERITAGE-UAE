import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AuthLayout } from '@/layouts/AuthLayout'
import { describeAuthError } from '@/lib/auth-errors'
import { forgotPasswordSchema, type ForgotPasswordValues } from '@/schemas/auth'
import { requestPasswordReset } from '@/services/auth.service'

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  })

  const onSubmit = handleSubmit(async ({ email }) => {
    setFormError(null)
    try {
      await requestPasswordReset(email)
      setSent(true)
    } catch (err) {
      const { kind, message } = describeAuthError(err)
      // Only connectivity / throttling are reported. Any other outcome looks identical to success, so the
      // form can never be used to discover which email addresses have accounts.
      if (kind === 'network' || kind === 'rate_limited') setFormError(message)
      else setSent(true)
    }
  })

  return (
    <AuthLayout
      title="Reset your password"
      description="Enter your email and we will send a reset link if an account exists."
      footer={
        <Link to="/login" className="underline underline-offset-4 hover:text-white">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <p
          role="status"
          className="flex gap-2 rounded-md bg-secondary p-3 text-sm text-secondary-foreground"
        >
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
          If an account exists for that email, a password reset link is on its way. Open the link in
          this same browser.
        </p>
      ) : (
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
              autoComplete="email"
              inputMode="email"
              autoFocus
              {...register('email')}
            />
          </FormField>
          <Button type="submit" disabled={isSubmitting} className="w-full">
            {isSubmitting ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {isSubmitting ? 'Sending…' : 'Send reset link'}
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
