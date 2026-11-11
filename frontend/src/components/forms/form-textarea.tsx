import type { ComponentProps } from 'react'
import type { FieldError } from 'react-hook-form'
import { FormField } from '@/components/common/form-field'
import { Textarea } from '@/components/ui/textarea'

interface FormTextareaProps extends Omit<ComponentProps<typeof Textarea>, 'id'> {
  label: string
  error?: FieldError | string
  description?: string
}

export function FormTextarea({
  label,
  error,
  description,
  required,
  className,
  ...props
}: FormTextareaProps) {
  return (
    <FormField
      label={label}
      error={error}
      description={description}
      required={required}
      className={className}
    >
      <Textarea required={required} {...props} />
    </FormField>
  )
}
