import type { ComponentProps } from 'react'
import type { FieldError } from 'react-hook-form'
import { FormField } from '@/components/common/form-field'
import { Input } from '@/components/ui/input'

interface FormDatePickerProps extends Omit<ComponentProps<typeof Input>, 'id' | 'type'> {
  label: string
  error?: FieldError | string
  description?: string
}

/**
 * Date field using the browser's native picker (accessible, touch friendly, no extra dependency). Values are
 * YYYY-MM-DD strings, the format the API uses. Pass `max={dubaiToday()}` where future dates are not allowed.
 */
export function FormDatePicker({
  label,
  error,
  description,
  required,
  className,
  ...props
}: FormDatePickerProps) {
  return (
    <FormField
      label={label}
      error={error}
      description={description}
      required={required}
      className={className}
    >
      <Input type="date" required={required} {...props} />
    </FormField>
  )
}
