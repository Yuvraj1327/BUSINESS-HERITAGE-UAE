import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface FormActionsProps {
  submitLabel?: string
  cancelLabel?: string
  /** Renders a Cancel button when given. */
  onCancel?: () => void
  isSubmitting?: boolean
  disabled?: boolean
  /** Extra controls placed before Cancel (e.g. a secondary action). */
  children?: ReactNode
  className?: string
}

/** Standard form footer: Cancel + Submit, right-aligned on wide screens, full-width stacked on phones. */
export function FormActions({
  submitLabel = 'Save',
  cancelLabel = 'Cancel',
  onCancel,
  isSubmitting = false,
  disabled = false,
  children,
  className,
}: FormActionsProps) {
  return (
    <div
      className={cn(
        'flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:items-center sm:justify-end',
        className,
      )}
    >
      {children}
      {onCancel ? (
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
          className="h-11 sm:h-9"
        >
          {cancelLabel}
        </Button>
      ) : null}
      <Button type="submit" disabled={disabled || isSubmitting} className="h-11 sm:h-9">
        {isSubmitting ? <Loader2 className="animate-spin" aria-hidden /> : null}
        {submitLabel}
      </Button>
    </div>
  )
}
