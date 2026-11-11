import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface SectionCardProps {
  title: string
  description?: string
  /** Header-right actions (e.g. a link or button). */
  actions?: ReactNode
  children: ReactNode
  className?: string
  contentClassName?: string
}

/** A titled white surface for one section of a page (chart, table, list, form group). */
export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
  contentClassName,
}: SectionCardProps) {
  return (
    <section className={cn('min-w-0 rounded-2xl border bg-card shadow-card', className)}>
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-sky-100 px-4 py-3.5 sm:px-5">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-primary">{title}</h2>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </header>
      <div className={cn('p-4 sm:p-5', contentClassName)}>{children}</div>
    </section>
  )
}
