import { useId, type ReactElement, cloneElement, isValidElement } from 'react'
import type { FieldError } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface FormFieldProps {
  label: string
  /** Pass the react-hook-form error (`errors.field`) or a plain message. */
  error?: FieldError | string
  description?: string
  required?: boolean
  className?: string
  children: ReactElement<{ id?: string; 'aria-invalid'?: boolean; 'aria-describedby'?: string }>
}

/** Label + control + hint/error, wired for accessibility. Works with react-hook-form `register`/`Controller`. */
export function FormField({
  label,
  error,
  description,
  required,
  className,
  children,
}: FormFieldProps) {
  const id = useId()
  const message = typeof error === 'string' ? error : error?.message
  const describedBy = message ? `${id}-error` : description ? `${id}-hint` : undefined
  const control = isValidElement(children)
    ? cloneElement(children, {
        id,
        'aria-invalid': message ? true : undefined,
        'aria-describedby': describedBy,
      })
    : children
  return (
    <div className={cn('grid gap-1.5', className)}>
      <Label htmlFor={id}>
        {label}
        {required ? (
          <span className="text-destructive" aria-hidden>
            {' '}
            *
          </span>
        ) : null}
      </Label>
      {control}
      {message ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {message}
        </p>
      ) : description ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
    </div>
  )
}
