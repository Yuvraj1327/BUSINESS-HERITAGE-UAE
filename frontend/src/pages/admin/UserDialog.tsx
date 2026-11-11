import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { FormActions } from '@/components/forms/form-actions'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { PasswordInput } from '@/components/ui/password-input'
import { FormField } from '@/components/common/form-field'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useBranches } from '@/hooks/use-branches'
import { useCreateUser } from '@/hooks/use-users'
import { toApiError } from '@/lib/errors'
import { userCreateSchema, type UserCreateValues } from '@/schemas/users'

function UserForm({ onDone }: { onDone: () => void }) {
  const branches = useBranches()
  const create = useCreateUser()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<UserCreateValues>({
    resolver: zodResolver(userCreateSchema),
    defaultValues: { email: '', full_name: '', branch_id: '', password: '', confirm_password: '' },
  })
  const { errors } = form.formState

  async function submit(v: UserCreateValues) {
    setError(null)
    try {
      await create.mutateAsync(v)
      form.reset() // drop the passwords from memory
      toast.success(
        'Branch User created. They can sign in now and must change the password on first login.',
      )
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in v) form.setError(field as keyof UserCreateValues, { message: msgs[0] })
      }
      setError(err.message)
    }
  }

  return (
    <form
      onSubmit={form.handleSubmit(submit)}
      noValidate
      aria-label="New user form"
      className="space-y-4"
    >
      {error ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}
      <FormInput
        label="Full name"
        required
        maxLength={150}
        error={errors.full_name}
        {...form.register('full_name')}
      />
      <FormInput
        label="Email"
        type="email"
        required
        autoComplete="off"
        error={errors.email}
        {...form.register('email')}
      />
      <Controller
        control={form.control}
        name="branch_id"
        render={({ field }) => (
          <FormSelect
            label="Branch"
            required
            value={field.value}
            onValueChange={field.onChange}
            placeholder={branches.isError ? 'Branches unavailable' : 'Select a branch'}
            error={errors.branch_id}
            options={(branches.data ?? [])
              .filter((b) => b.is_active)
              .map((b) => ({ value: b.id, label: b.name }))}
          />
        )}
      />
      <FormField
        label="Password"
        error={errors.password}
        description="Initial password. Share it with the user securely; they must change it on first login."
      >
        <PasswordInput autoComplete="new-password" {...form.register('password')} />
      </FormField>
      <FormField label="Confirm password" error={errors.confirm_password}>
        <PasswordInput autoComplete="new-password" {...form.register('confirm_password')} />
      </FormField>
      <FormActions submitLabel="Create user" isSubmitting={create.isPending} onCancel={onDone} />
    </form>
  )
}

export function UserDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Branch User</DialogTitle>
          <DialogDescription>
            You set an initial password; the user can sign in immediately and is required to choose
            their own password on first login. No email is sent. Owner accounts are created by an
            operator, not here.
          </DialogDescription>
        </DialogHeader>
        <UserForm onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}
