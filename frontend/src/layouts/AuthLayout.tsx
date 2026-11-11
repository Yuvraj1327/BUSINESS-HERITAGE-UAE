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
    <div className="flex min-h-dvh flex-col bg-sidebar px-4 py-8">
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6">
        <Brand light stacked className="justify-center" />
        <div className="rounded-xl border bg-card p-6 shadow-lg sm:p-8">
          <h1 className="text-xl font-semibold text-primary">{title}</h1>
          {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
          <div className="mt-6">{children}</div>
        </div>
        {footer ? <div className="text-center text-sm text-white/80">{footer}</div> : null}
      </div>
      <p className="mt-6 text-center text-xs text-white/60">{APP_NAME} · Management System</p>
    </div>
  )
}
