import type { ReactNode } from 'react'
import { PageHero } from '@/components/layout/page-hero'
import { cn } from '@/lib/utils'

interface PageContainerProps {
  title: string
  description?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}

/** Standard page frame: responsive width and padding, a PageHero band, then the page's sections. */
export function PageContainer({
  title,
  description,
  actions,
  children,
  className,
}: PageContainerProps) {
  return (
    <section
      className={cn(
        'mx-auto w-full max-w-7xl min-w-0 space-y-6 px-4 py-5 sm:px-6 sm:py-6 lg:px-8',
        className,
      )}
    >
      <PageHero title={title} description={description} actions={actions} />
      {children}
    </section>
  )
}
