import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { FormActions } from '@/components/forms/form-actions'
import { FormDatePicker } from '@/components/forms/form-date-picker'
import { FormInput } from '@/components/forms/form-input'
import { FormSelect } from '@/components/forms/form-select'
import { FormTextarea } from '@/components/forms/form-textarea'
import { useBranchContext } from '@/components/layout/branch-context'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useCreateEmployee, useUpdateEmployee } from '@/hooks/use-hr'
import { toApiError } from '@/lib/errors'
import {
  employeeFormSchema,
  type Employee,
  type EmployeeFormInput,
  type EmployeeFormValues,
} from '@/schemas/hr'

const blank: EmployeeFormInput = {
  full_name: '',
  branch_id: '',
  role_title: '',
  monthly_salary: '',
  passport_expiry: '',
  visa_expiry: '',
  notes: '',
  reason: '',
}

function EmployeeForm({
  employee,
  onSaved,
  onDone,
}: {
  employee?: Employee | null
  onSaved?: (id: string) => void
  onDone: () => void
}) {
  const { branches } = useBranchContext()
  const form = useForm<EmployeeFormInput, unknown, EmployeeFormValues>({
    resolver: zodResolver(employeeFormSchema),
    defaultValues: employee
      ? {
          full_name: employee.full_name,
          branch_id: employee.branch_id,
          role_title: employee.role_title ?? '',
          monthly_salary: employee.monthly_salary,
          passport_expiry: employee.passport_expiry ?? '',
          visa_expiry: employee.visa_expiry ?? '',
          notes: employee.notes ?? '',
          reason: '',
        }
      : blank,
  })
  const create = useCreateEmployee()
  const update = useUpdateEmployee()
  const [error, setError] = useState<string | null>(null)
  const { errors } = form.formState
  const [salary, branch, passport, visa] = useWatch({
    control: form.control,
    name: ['monthly_salary', 'branch_id', 'passport_expiry', 'visa_expiry'],
  })
  // A reason is needed (and shown) only when a sensitive field is being changed on an existing employee.
  const sensitive =
    !!employee &&
    (salary !== employee.monthly_salary ||
      branch !== employee.branch_id ||
      passport !== (employee.passport_expiry ?? '') ||
      visa !== (employee.visa_expiry ?? ''))

  async function submit(v: EmployeeFormValues) {
    setError(null)
    if (sensitive && v.reason.length < 3) {
      form.setError('reason', { message: 'Enter a reason (at least 3 characters)' })
      return
    }
    const body = {
      full_name: v.full_name,
      branch_id: v.branch_id,
      monthly_salary: v.monthly_salary,
      ...(v.role_title ? { role_title: v.role_title } : {}),
      ...(v.passport_expiry ? { passport_expiry: v.passport_expiry } : {}),
      ...(v.visa_expiry ? { visa_expiry: v.visa_expiry } : {}),
      ...(v.notes ? { notes: v.notes } : {}),
      ...(sensitive && v.reason ? { reason: v.reason } : {}),
    }
    try {
      const saved = employee
        ? await update.mutateAsync({ id: employee.id, body })
        : await create.mutateAsync(body)
      toast.success(employee ? 'Employee updated' : 'Employee added')
      onSaved?.(saved.employee.id)
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in blank) form.setError(field as keyof EmployeeFormInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }

  return (
    <form
      onSubmit={form.handleSubmit(submit)}
      noValidate
      aria-label="Employee form"
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
      <div className="grid gap-4 sm:grid-cols-2">
        <Controller
          control={form.control}
          name="branch_id"
          render={({ field }) => (
            <FormSelect
              label="Assigned branch"
              required
              value={field.value || ''}
              onValueChange={field.onChange}
              options={branches
                .filter((b) => b.is_active)
                .map((b) => ({ value: b.id, label: b.name }))}
              error={errors.branch_id}
            />
          )}
        />
        <FormInput
          label="Job role"
          maxLength={100}
          error={errors.role_title}
          {...form.register('role_title')}
        />
      </div>
      <FormInput
        label="Monthly salary (AED)"
        required
        inputMode="decimal"
        autoComplete="off"
        error={errors.monthly_salary}
        {...form.register('monthly_salary')}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormDatePicker
          label="Visa expiry date"
          error={errors.visa_expiry}
          {...form.register('visa_expiry')}
        />
        <FormDatePicker
          label="Passport expiry date"
          description="Expiry date only: passport and Emirates ID numbers are never stored."
          error={errors.passport_expiry}
          {...form.register('passport_expiry')}
        />
      </div>
      <FormTextarea
        label="Notes"
        maxLength={1000}
        error={errors.notes}
        {...form.register('notes')}
      />
      {sensitive ? (
        <FormTextarea
          label="Reason for the change"
          required
          maxLength={500}
          description="Salary, branch and visa/passport changes are kept in the audit history."
          error={errors.reason}
          {...form.register('reason')}
        />
      ) : null}
      <FormActions
        submitLabel={employee ? 'Save changes' : 'Add employee'}
        isSubmitting={create.isPending || update.isPending}
        onCancel={onDone}
      />
    </form>
  )
}

export function EmployeeDialog({
  open,
  onOpenChange,
  employee,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  employee?: Employee | null
  onSaved?: (id: string) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{employee ? 'Edit employee' : 'Add employee'}</DialogTitle>
          <DialogDescription>
            Status is changed with its own action (leave, return, visa cancellation), not typed
            here.
          </DialogDescription>
        </DialogHeader>
        <EmployeeForm employee={employee} onSaved={onSaved} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  )
}
