import type { ReactNode } from 'react'
import { Brand } from '@/components/layout/brand'
import { APP_NAME } from '@/constants'

/** Centered card on a navy backdrop for login / reset pages. Responsive down to small phones. */
export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-hidden bg-[#6f9ccb] px-4 py-8 lg:px-[7vw]">
      {/* Responsive hero backdrop: portrait art on phones, 16:9 art from `md` up. Width/height reserve the
          aspect ratio; object-cover keeps it undistorted and anchors the subject (bottom / bottom-right). */}
      <picture className="absolute inset-0 -z-10">
        <source
          media="(min-width: 768px)"
          type="image/webp"
          srcSet="/hero-desktop.webp"
          width={1672}
          height={941}
        />
        <source media="(min-width: 768px)" srcSet="/hero-desktop.png" width={1672} height={941} />
        <source type="image/webp" srcSet="/hero-mobile.webp" width={941} height={1672} />
        <img
          src="/hero-mobile.png"
          alt=""
          width={941}
          height={1672}
          fetchPriority="high"
          decoding="async"
          draggable={false}
          className="size-full object-cover object-bottom md:object-[85%_100%]"
        />
      </picture>
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 lg:mx-0">
        <div className="mx-auto w-fit rounded-full bg-white/20 p-2 shadow-lg backdrop-blur-sm">
          <Brand light stacked className="justify-center" />
        </div>
        <div className="rounded-xl border bg-card p-6 shadow-lg sm:p-8">
          <h1 className="text-xl font-semibold text-primary">{title}</h1>
          {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
          <div className="mt-6">{children}</div>
        </div>
        {footer ? (
          <div className="mx-auto w-fit rounded-full bg-sidebar/90 px-4 py-2 text-center text-sm text-white/90 backdrop-blur-sm">
            {footer}
          </div>
        ) : null}
      </div>
      <p className="mt-6 text-center text-xs text-foreground/70">{APP_NAME} · Management System</p>
    </div>
  )
}
