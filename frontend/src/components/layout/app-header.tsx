import { PanelLeft, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import type { ReactNode } from 'react'
import { Brand } from '@/components/layout/brand'
import { Breadcrumbs } from '@/components/layout/breadcrumbs'
import { NotificationMenu } from '@/components/layout/notification-menu'
import { UserMenu } from '@/components/layout/user-menu'
import { Button } from '@/components/ui/button'
import { BUSINESS_TIMEZONE } from '@/constants'
import { useLayoutMode } from '@/hooks/use-media-query'
import { dubaiToday } from '@/utils/format'

/** The drawer is opened without a Radix trigger, so it hands focus back to this button by id when it closes. */
export const NAV_TOGGLE_ID = 'app-nav-toggle'

function todayLabel(now = new Date()): string {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: BUSINESS_TIMEZONE,
  }).format(now)
}

interface AppHeaderProps {
  /** Whether the toggle opens the drawer, or collapses/expands the desktop sidebar. */
  toggle: { kind: 'drawer' } | { kind: 'collapse'; collapsed: boolean }
  onToggle: () => void
  /** Role-specific control (branch selector for Owner, assigned branch for Branch User). */
  extra?: ReactNode
}

export function AppHeader({ toggle, onToggle, extra }: AppHeaderProps) {
  const mobile = useLayoutMode() === 'mobile'
  const label =
    toggle.kind === 'drawer'
      ? 'Open navigation'
      : toggle.collapsed
        ? 'Expand sidebar'
        : 'Collapse sidebar'
  const Icon =
    toggle.kind === 'drawer' ? PanelLeft : toggle.collapsed ? PanelLeftOpen : PanelLeftClose
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-card px-3 shadow-sm sm:px-4">
      <Button
        variant="ghost"
        size="icon"
        className="size-11 shrink-0 md:size-9"
        id={NAV_TOGGLE_ID}
        aria-label={label}
        aria-expanded={toggle.kind === 'collapse' ? !toggle.collapsed : undefined}
        onClick={onToggle}
      >
        <Icon aria-hidden />
      </Button>
      {mobile ? (
        <div className="flex min-w-0 flex-1 justify-center">
          <Brand compactText />
        </div>
      ) : (
        <Breadcrumbs className="flex-1" />
      )}
      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {extra ? <div>{extra}</div> : null}
        <time
          dateTime={dubaiToday()}
          className="hidden text-sm whitespace-nowrap text-muted-foreground xl:block"
        >
          {todayLabel()}
        </time>
        <NotificationMenu />
        {mobile ? null : <UserMenu />}
      </div>
    </header>
  )
}
