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
  className?: string
}

export function StatCard({
  label,
  value,
  description,
  icon: Icon,
  isLoading = false,
  placeholder = false,
  className,
}: StatCardProps) {
  return (
    <Card
      className={cn(
        'gap-2 p-4 shadow-card',
        placeholder && 'border-dashed bg-card/60 shadow-none',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        {Icon ? <Icon className="size-4 text-teal" aria-hidden /> : null}
      </div>
      {isLoading ? (
        <Skeleton className="h-8 w-24" />
      ) : (
        <p className="tabular text-2xl font-semibold text-primary">
          {value ?? <span aria-label="No data yet">—</span>}
        </p>
      )}
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
    </Card>
  )
}
