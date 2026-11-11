import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
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
import { useAssignees, useCreateTask, useUpdateTask } from '@/hooks/use-tasks'
import { toApiError } from '@/lib/errors'
import { taskFormSchema, type Task, type TaskFormInput } from '@/schemas/tasks'

const ALL = '__all__'
const NONE = '__none__'

function TaskForm({ task, onDone }: { task?: Task; onDone: () => void }) {
  const { branches } = useBranchContext()
  const assignees = useAssignees()
  const create = useCreateTask()
  const update = useUpdateTask()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<TaskFormInput>({
    resolver: zodResolver(taskFormSchema),
    defaultValues: {
      title: task?.title ?? '',
      description: task?.description ?? '',
      branch_id: task ? (task.branch_id ?? ALL) : ALL,
      due_date: task?.due_date ?? '',
      assignee_id: task?.assignee_id ?? NONE,
      notes: task?.notes ?? '',
      reason: '',
    },
  })
  const { errors, isSubmitting } = form.formState
  async function submit(v: TaskFormInput) {
    setError(null)
    const body = {
      title: v.title,
      description: v.description || null,
      branch_id: v.branch_id === ALL ? null : v.branch_id,
      due_date: v.due_date || null,
      assignee_id: v.assignee_id === NONE ? null : v.assignee_id,
      notes: v.notes || null,
    }
    try {
      if (task) {
        await update.mutateAsync({
          id: task.id,
          body: { ...body, ...(v.reason ? { reason: v.reason } : {}) },
        })
        toast.success('Task updated')
      } else {
        await create.mutateAsync(body)
        toast.success('Task created')
      }
      onDone()
    } catch (e) {
      const err = toApiError(e)
      for (const [field, msgs] of Object.entries(err.fields)) {
        if (field in form.getValues())
          form.setError(field as keyof TaskFormInput, { message: msgs[0] })
      }
      setError(err.message)
    }
  }
  return (
    <form noValidate className="space-y-4" aria-label="Task" onSubmit={form.handleSubmit(submit)}>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <FormInput
        label="Title"
        required
        maxLength={200}
        error={errors.title}
        {...form.register('title')}
      />
      <FormTextarea
        label="Description"
        maxLength={2000}
        error={errors.description}
        {...form.register('description')}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Controller
          control={form.control}
          name="branch_id"
          render={({ field }) => (
            <FormSelect
              label="Branch"
              value={field.value}
              onValueChange={field.onChange}
              options={[
                { value: ALL, label: 'All Branches' },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
          )}
        />
        <FormDatePicker label="Due date" error={errors.due_date} {...form.register('due_date')} />
        <Controller
          control={form.control}
          name="assignee_id"
          render={({ field }) => (
            <FormSelect
              label="Assigned to"
              description="New tasks start Unassigned."
              value={field.value}
              onValueChange={field.onChange}
              options={[
                { value: NONE, label: 'Unassigned' },
                ...(assignees.data ?? []).map((a) => ({
                  value: a.id,
                  label: a.branch_name ? `${a.name} (${a.branch_name})` : a.name,
                })),
              ]}
            />
          )}
        />
      </div>
      <FormTextarea
        label="Notes"
        maxLength={2000}
        error={errors.notes}
        {...form.register('notes')}
      />
      {task ? (
        <FormInput
          label="Reason for the change (optional, kept in the history)"
          maxLength={500}
          error={errors.reason}
          {...form.register('reason')}
        />
      ) : null}
      <FormActions
        submitLabel={task ? 'Save changes' : 'Create task'}
        onCancel={onDone}
        isSubmitting={isSubmitting}
      />
    </form>
  )
}

export function TaskDialog({
  open,
  onOpenChange,
  task,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  task?: Task
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{task ? 'Edit task' : 'New task'}</DialogTitle>
          <DialogDescription>
            {task
              ? 'Change the details, branch or assignee. Every change is recorded in the history.'
              : 'Tasks start as To Do and Unassigned.'}
          </DialogDescription>
        </DialogHeader>
        {open ? <TaskForm {...(task ? { task } : {})} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  )
}
