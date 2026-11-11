import { useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/components/layout/page-header'

/**
 * Page header band: title, description and actions on a soft blue gradient. With `banner`, the laundry image sits on
 * the right (decorative, omitted if the file is missing).
 */
export function PageHero({
  title,
  description,
  actions,
  banner = false,
}: {
  title: string
  description?: string
  actions?: ReactNode
  /** Show the laundry banner on the right. Dashboard only: elsewhere it would sit behind the text. */
  banner?: boolean
}) {
  const [bannerOk, setBannerOk] = useState(true)
  return (
    <div className="relative min-h-28 overflow-hidden rounded-2xl bg-gradient-to-r from-white via-sky-50 to-sky-100 ring-1 ring-sky-100">
      <div
        className={cn(
          'relative z-10 px-4 py-4 sm:px-8 sm:py-6',
          banner && 'max-w-[62%] sm:max-w-[55%]',
        )}
      >
        <PageHeader
          title={title}
          description={description}
          actions={actions}
          className="[&_h1]:text-xl sm:[&_h1]:text-3xl"
        />
      </div>
      {banner && bannerOk ? (
        <img
          src="/dashboard-banner.png"
          alt=""
          aria-hidden
          draggable={false}
          onError={() => setBannerOk(false)}
          className="pointer-events-none absolute inset-y-0 right-0 h-full w-auto max-w-[55%] object-cover object-right [mask-image:linear-gradient(to_right,transparent,black_25%)] "
        />
      ) : null}
    </div>
  )
}
