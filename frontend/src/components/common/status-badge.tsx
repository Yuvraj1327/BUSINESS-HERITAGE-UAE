import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type Status = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const VARIANT = {
  success: 'success',
  warning: 'warning',
  danger: 'destructive',
  info: 'info',
  neutral: 'neutral',
} as const

const DOT = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-destructive',
  info: 'bg-blue-700',
  neutral: 'bg-muted-foreground',
} as const

/** Status pill: colour plus a dot plus the word, so meaning never depends on colour alone. */
export function StatusBadge({
  status,
  children,
  className,
}: {
  status: Status
  children: string
  className?: string
}) {
  return (
    <Badge variant={VARIANT[status]} className={cn('gap-1.5', className)}>
      <span aria-hidden className={cn('size-1.5 rounded-full', DOT[status])} />
      {children}
    </Badge>
  )
}
