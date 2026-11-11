import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface LoadingStateProps {
  /** Number of placeholder lines. */
  rows?: number
  label?: string
  className?: string
}

/** Content skeleton for a section that is loading (for a bare spinner use LoadingIndicator). */
export function LoadingState({ rows = 3, label = 'Loading…', className }: LoadingStateProps) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={cn('space-y-3', className)}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cn('h-5', i === rows - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  )
}
