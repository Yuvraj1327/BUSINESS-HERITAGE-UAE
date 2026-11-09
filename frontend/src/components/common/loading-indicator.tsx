import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface LoadingIndicatorProps {
  label?: string
  className?: string
  /** Fill the available area and centre the spinner. */
  fill?: boolean
}

export function LoadingIndicator({
  label = 'Loading…',
  className,
  fill = false,
}: LoadingIndicatorProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex items-center justify-center gap-2 text-sm text-muted-foreground',
        fill && 'min-h-48 w-full',
        className,
      )}
    >
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  )
}
