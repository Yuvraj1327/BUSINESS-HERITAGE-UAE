import type { FieldError } from 'react-hook-form'
import { FormField } from '@/components/common/form-field'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export interface SelectOption {
  value: string
  label: string
}

interface FormSelectProps {
  label: string
  options: SelectOption[]
  value?: string
  onValueChange?: (value: string) => void
  placeholder?: string
  error?: FieldError | string
  description?: string
  required?: boolean
  disabled?: boolean
  name?: string
  className?: string
}

/** Labelled select. With react-hook-form use <Controller> and pass field.value / field.onChange. */
export function FormSelect({
  label,
  options,
  value,
  onValueChange,
  placeholder = 'Select…',
  error,
  description,
  required,
  disabled,
  name,
  className,
}: FormSelectProps) {
  return (
    <Select
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
      name={name}
      required={required}
    >
      <FormField
        label={label}
        error={error}
        description={description}
        required={required}
        className={className}
      >
        <SelectTrigger>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
      </FormField>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
