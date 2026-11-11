import { NavLink, Outlet } from 'react-router-dom'
import { PageContainer } from '@/components/layout/page-container'
import { SETTINGS_PAGES } from '@/config/navigation'
import { cn } from '@/lib/utils'

/**
 * Frame for every Settings page: a menu (vertical on wide screens, a scrolling row on phones) and the page.
 * These pages act only on the signed-in user's own account, so every signed-in user may open them.
 */
export function SettingsLayout() {
  return (
    <PageContainer
      title="Settings"
      description="Manage your own profile, security and preferences."
    >
      <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-6">
        <nav aria-label="Settings sections" className="min-w-0">
          <ul className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
            {SETTINGS_PAGES.map(({ slug, label, icon: Icon, blurb }) => (
              <li key={slug} className="shrink-0 lg:shrink">
                <NavLink
                  to={`/settings/${slug}`}
                  className={({ isActive }) =>
                    cn(
                      'flex min-h-11 items-center gap-3 rounded-xl border px-3 py-2 text-sm transition-colors hover:bg-muted',
                      isActive
                        ? 'border-accent bg-secondary font-semibold text-primary'
                        : 'border-transparent text-foreground',
                    )
                  }
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  <span className="min-w-0">
                    <span className="block whitespace-nowrap lg:whitespace-normal">{label}</span>
                    <span className="hidden text-xs font-normal text-muted-foreground lg:block">
                      {blurb}
                    </span>
                  </span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="min-w-0 space-y-6">
          <Outlet />
        </div>
      </div>
    </PageContainer>
  )
}
