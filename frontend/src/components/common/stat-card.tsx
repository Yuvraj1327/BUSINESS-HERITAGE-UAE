import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface StatCardProps {
  label: string
  /** The figure. Omit (with `placeholder`) before data exists: the card shows a dash, never a made-up number. */
  value?: ReactNode
  description?: string
  icon?: LucideIcon
  isLoading?: boolean
  /** Layout placeholder: dashed, value shown as an em dash. */
  placeholder?: boolean
  /** Soft colour accent for the icon tile and card wash. */
  tone?: 'blue' | 'green' | 'amber' | 'purple'
  className?: string
}

const TONES = {
  blue: { card: 'bg-gradient-to-br from-white to-sky-50', tile: 'bg-sky-100 text-sky-700' },
  green: {
    card: 'bg-gradient-to-br from-white to-emerald-50',
    tile: 'bg-emerald-100 text-emerald-700',
  },
  amber: { card: 'bg-gradient-to-br from-white to-amber-50', tile: 'bg-amber-100 text-amber-700' },
  purple: {
    card: 'bg-gradient-to-br from-white to-violet-50',
    tile: 'bg-violet-100 text-violet-700',
  },
} as const

export function StatCard({
  label,
  value,
  description,
  icon: Icon,
  isLoading = false,
  placeholder = false,
  tone,
  className,
}: StatCardProps) {
  return (
    <Card
      className={cn(
        'gap-1.5 p-3 shadow-card sm:gap-2 sm:p-4',
        tone && TONES[tone].card,
        placeholder && 'border-dashed bg-card/60 shadow-none',
        className,
      )}
    >
      <div className="flex items-center gap-2 sm:gap-3">
        {Icon && tone ? (
          <span
            className={cn(
              'grid size-8 shrink-0 place-items-center rounded-lg sm:size-10',
              TONES[tone].tile,
            )}
          >
            <Icon className="size-4 sm:size-5" aria-hidden />
          </span>
        ) : null}
        <p className="min-w-0 flex-1 text-sm leading-tight font-medium text-muted-foreground">
          {label}
        </p>
        {Icon && !tone ? <Icon className="size-4 text-teal" aria-hidden /> : null}
      </div>
      {isLoading ? (
        <Skeleton className="h-8 w-24" />
      ) : (
        <p className="tabular text-xl font-semibold break-words text-primary sm:text-2xl">
          {value ?? <span aria-label="No data yet">—</span>}
        </p>
      )}
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
    </Card>
  )
}
