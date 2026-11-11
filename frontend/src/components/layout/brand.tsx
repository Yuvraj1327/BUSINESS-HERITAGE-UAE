import { WashingMachine } from 'lucide-react'
import { APP_NAME } from '@/constants'
import { cn } from '@/lib/utils'

export function Brand({
  className,
  light = false,
  compact = false,
}: {
  className?: string
  light?: boolean
  /** Logo mark only (icon rail). The name stays available to screen readers. */
  compact?: boolean
}) {
  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <span
        className={cn(
          'grid size-9 place-items-center rounded-lg',
          light ? 'bg-white/10 text-white' : 'bg-primary text-primary-foreground',
        )}
      >
        <WashingMachine className="size-5" aria-hidden />
      </span>
      <span className={cn('leading-tight', compact && 'sr-only')}>
        <span
          className={cn(
            'block text-sm font-semibold tracking-wide',
            light ? 'text-white' : 'text-primary',
          )}
        >
          ALSAFA
        </span>
        <span
          className={cn('block text-[11px]', light ? 'text-white/70' : 'text-muted-foreground')}
        >
          {APP_NAME.replace('ALSAFA ', '')}
        </span>
      </span>
    </div>
  )
}
