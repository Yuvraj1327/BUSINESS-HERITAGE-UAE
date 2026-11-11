import { ChevronRight } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { buildBreadcrumbs } from '@/lib/breadcrumbs'
import { cn } from '@/lib/utils'

/** Breadcrumb trail for the current route. On small screens only the current page is shown (it is the title). */
export function Breadcrumbs({ className }: { className?: string }) {
  const { pathname } = useLocation()
  const crumbs = buildBreadcrumbs(pathname)
  return (
    <nav aria-label="Breadcrumb" className={cn('min-w-0', className)}>
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {crumbs.map((crumb, i) => {
          const last = i === crumbs.length - 1
          return (
            <li
              key={`${i}-${crumb.label}`}
              className={cn('flex min-w-0 items-center gap-1.5', !last && 'max-sm:hidden')}
            >
              {crumb.to && !last ? (
                <Link
                  to={crumb.to}
                  className="rounded-sm text-muted-foreground hover:text-primary hover:underline"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span
                  aria-current={last ? 'page' : undefined}
                  className={cn(
                    'truncate',
                    last ? 'font-semibold text-primary' : 'text-muted-foreground',
                  )}
                >
                  {crumb.label}
                </span>
              )}
              {last ? null : (
                <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
