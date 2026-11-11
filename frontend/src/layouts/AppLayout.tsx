import { useEffect, useState, type ReactNode } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { AppHeader, NAV_TOGGLE_ID } from '@/components/layout/app-header'
import { AppSidebar, SidebarContent } from '@/components/layout/app-sidebar'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { APP_NAME } from '@/constants'
import { useLayoutMode } from '@/hooks/use-media-query'
import { buildBreadcrumbs } from '@/lib/breadcrumbs'
import { cn } from '@/lib/utils'

const COLLAPSE_KEY = 'alsafa.sidebar.collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

interface AppLayoutProps {
  /** Role-specific header control (branch selector or assigned-branch label). */
  headerExtra?: ReactNode
  /** Page content. Defaults to the matched child route. */
  children?: ReactNode
}

/**
 * The application shell shared by every role: sidebar (desktop), icon rail (tablet) or drawer (mobile),
 * header with breadcrumbs, and the content area. Role differences are injected by OwnerLayout / BranchLayout;
 * what the navigation contains is decided by the user's permissions, not by which layout this is.
 */
export function AppLayout({ headerExtra, children }: AppLayoutProps) {
  const mode = useLayoutMode()
  const { pathname } = useLocation()
  const [collapsed, setCollapsed] = useState(readCollapsed)
  // The drawer is open for one location only, so navigating anywhere closes it without an effect.
  const [drawerPath, setDrawerPath] = useState<string | null>(null)
  const drawerOpen = drawerPath === pathname && mode !== 'desktop'

  const rail = mode === 'tablet' || (mode === 'desktop' && collapsed)

  useEffect(() => {
    const page = buildBreadcrumbs(pathname).at(-1)?.label
    document.title = page && pathname !== '/' ? `${page} · ${APP_NAME}` : APP_NAME
  }, [pathname])

  function toggleSidebar() {
    if (mode === 'desktop') {
      setCollapsed((c) => {
        try {
          localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1')
        } catch {
          /* storage unavailable: the choice lasts for this page view */
        }
        return !c
      })
    } else {
      setDrawerPath(pathname)
    }
  }

  return (
    <TooltipProvider delayDuration={150}>
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-card px-3 py-2 text-sm font-medium text-primary shadow-pop focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to main content
      </a>

      {mode !== 'mobile' ? <AppSidebar rail={rail} /> : null}

      {mode !== 'desktop' ? (
        <Sheet open={drawerOpen} onOpenChange={(open) => setDrawerPath(open ? pathname : null)}>
          <SheetContent
            closeLabel="Close navigation"
            onCloseAutoFocus={(event) => {
              event.preventDefault()
              document.getElementById(NAV_TOGGLE_ID)?.focus()
            }}
          >
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <SheetDescription className="sr-only">Pages you can open</SheetDescription>
            <SidebarContent rail={false} onNavigate={() => setDrawerPath(null)} />
          </SheetContent>
        </Sheet>
      ) : null}

      <div
        className={cn(
          'flex min-h-dvh min-w-0 flex-col transition-[padding] duration-200 motion-reduce:transition-none',
          mode === 'mobile'
            ? 'pl-0'
            : rail
              ? 'pl-[var(--sidebar-rail-width)]'
              : 'pl-[var(--sidebar-width)]',
        )}
      >
        <AppHeader
          toggle={mode === 'desktop' ? { kind: 'collapse', collapsed } : { kind: 'drawer' }}
          onToggle={toggleSidebar}
          extra={mode === 'mobile' ? undefined : headerExtra}
        />
        {headerExtra && mode === 'mobile' ? (
          <div className="border-b bg-card px-3 py-2">{headerExtra}</div>
        ) : null}
        <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 outline-none">
          {children ?? <Outlet />}
        </main>
        <footer className="border-t bg-card px-4 py-3 text-center text-xs text-muted-foreground">
          {APP_NAME} · Management System
        </footer>
      </div>
    </TooltipProvider>
  )
}
