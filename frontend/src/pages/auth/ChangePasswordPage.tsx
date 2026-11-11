import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { useAuth } from '@/auth/use-auth'
import { FormField } from '@/components/common/form-field'
import { Button } from '@/components/ui/button'
import { PasswordInput } from '@/components/ui/password-input'
import { AuthLayout } from '@/layouts/AuthLayout'
import { describeAuthError } from '@/lib/auth-errors'
import { toApiError } from '@/lib/errors'
import { PASSWORD_MIN_LENGTH, strongPassword } from '@/schemas/auth'
import { changeInitialPassword, verifyCurrentPassword } from '@/services/auth.service'

const schema = z
  .object({
    currentPassword: z.string().min(1, 'Enter your current password'),
    password: strongPassword,
    confirmPassword: z.string().min(1, 'Confirm your new password'),
  })
  .refine((v) => v.password === v.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  })
  .refine((v) => v.password !== v.currentPassword, {
    path: ['password'],
    message: 'Choose a password different from the one you were given',
  })
type Values = z.infer<typeof schema>

/** Shown instead of the app while profile.must_change_password is true (first login with an Owner-issued password). */
export function ChangePasswordPage() {
  const auth = useAuth()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { currentPassword: '', password: '', confirmPassword: '' },
  })

  const onSubmit = handleSubmit(async ({ currentPassword, password, confirmPassword }) => {
    setFormError(null)
    try {
      await verifyCurrentPassword(auth.user?.email ?? '', currentPassword)
    } catch {
      setFormError('Your current password is not correct.')
      return
    }
    try {
      await changeInitialPassword(password, confirmPassword)
    } catch (err) {
      const apiError = toApiError(err)
      setFormError(
        apiError.fields.password?.[0] ??
          apiError.fields.new_password?.[0] ??
          (apiError.message || describeAuthError(err).message),
      )
      return
    }
    reset() // passwords leave memory
    auth.reloadProfile() // the flag is now cleared: the app opens
  })

  return (
    <AuthLayout
      title="Change your password"
      description="For security, you must replace the password you were given before using the system."
      footer={
        <button
          type="button"
          className="underline underline-offset-4 hover:text-white"
          onClick={() => void auth.signOut()}
        >
          Sign out
        </button>
      }
    >
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
        <FormField label="Current password" error={errors.currentPassword}>
          <PasswordInput
            autoComplete="current-password"
            autoFocus
            {...register('currentPassword')}
          />
        </FormField>
        <FormField
          label="New password"
          error={errors.password}
          description={`At least ${PASSWORD_MIN_LENGTH} characters, with upper and lower case letters and a number.`}
        >
          <PasswordInput autoComplete="new-password" {...register('password')} />
        </FormField>
        <FormField label="Confirm new password" error={errors.confirmPassword}>
          <PasswordInput autoComplete="new-password" {...register('confirmPassword')} />
        </FormField>
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {isSubmitting ? 'Saving…' : 'Change password'}
        </Button>
      </form>
    </AuthLayout>
  )
}
