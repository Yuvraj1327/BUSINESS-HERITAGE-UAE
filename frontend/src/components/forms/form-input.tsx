import type { ComponentProps } from 'react'
import type { FieldError } from 'react-hook-form'
import { FormField } from '@/components/common/form-field'
import { Input } from '@/components/ui/input'

interface FormInputProps extends Omit<ComponentProps<typeof Input>, 'id'> {
  label: string
  error?: FieldError | string
  description?: string
}

/** Labelled text input with hint/error. Works with react-hook-form `register(...)` spread onto it. */
export function FormInput({
  label,
  error,
  description,
  required,
  className,
  ...props
}: FormInputProps) {
  return (
    <FormField
      label={label}
      error={error}
      description={description}
      required={required}
      className={className}
    >
      <Input required={required} {...props} />
    </FormField>
  )
}
