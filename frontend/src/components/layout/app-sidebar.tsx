import { LogOut } from 'lucide-react'
import { useAuth } from '@/auth/use-auth'
import { useNavigation } from '@/auth/use-navigation'
import { Brand } from '@/components/layout/brand'
import { SidebarGroup } from '@/components/layout/sidebar-group'
import { SidebarItem } from '@/components/layout/sidebar-item'
import { UserAvatar } from '@/components/layout/user-avatar'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { roleLabel } from '@/utils/user'

interface SidebarContentProps {
  /** Icon-only rail (tablet, or desktop collapsed). The mobile drawer is never a rail. */
  rail: boolean
  onNavigate?: () => void
}

/** Brand, role-filtered navigation and the signed-in user. Shared by the fixed sidebar and the mobile drawer. */
export function SidebarContent({ rail, onNavigate }: SidebarContentProps) {
  const { profile, signOut } = useAuth()
  const sections = useNavigation()

  const signOutButton = (
    <button
      type="button"
      onClick={() => void signOut()}
      aria-label="Sign out"
      className={cn(
        'flex min-h-11 items-center gap-3 rounded-md text-sm text-sidebar-foreground hover:bg-sidebar-accent/70 hover:text-white focus-visible:outline-2 focus-visible:outline-white md:min-h-10',
        rail ? 'w-full justify-center' : 'w-full px-3',
      )}
    >
      <LogOut className="size-[18px] shrink-0" aria-hidden />
      {rail ? null : <span>Sign out</span>}
    </button>
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className={cn(
          'flex h-14 shrink-0 items-center border-b border-sidebar-border',
          rail ? 'justify-center' : 'px-4',
        )}
      >
        <Brand light compact={rail} />
      </div>

      <nav
        aria-label="Main"
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-3"
      >
        {sections.map((section, index) => (
          <div key={section.key} className={cn(index > 0 && 'mt-4')}>
            {rail ? (
              index > 0 ? (
                <div className="mx-2 mb-2 border-t border-sidebar-border" role="presentation" />
              ) : null
            ) : (
              <p
                className="px-3 pb-1.5 text-[11px] font-semibold tracking-wider text-sidebar-muted uppercase"
                id={`nav-section-${section.key}`}
              >
                {section.label}
              </p>
            )}
            <div
              className="space-y-0.5"
              role="group"
              aria-labelledby={rail ? undefined : `nav-section-${section.key}`}
              aria-label={rail ? section.label : undefined}
            >
              {section.items.map((item) =>
                item.children ? (
                  <SidebarGroup key={item.key} item={item} rail={rail} onNavigate={onNavigate} />
                ) : item.to ? (
                  <SidebarItem
                    key={item.key}
                    to={item.to}
                    label={
                      item.ownBranchLabel &&
                      profile &&
                      profile.permissions[item.module]?.scope === 'own_branch'
                        ? item.ownBranchLabel
                        : item.label
                    }
                    icon={item.icon}
                    rail={rail}
                    onNavigate={onNavigate}
                  />
                ) : null,
              )}
            </div>
          </div>
        ))}
      </nav>

      <div className="shrink-0 space-y-1 border-t border-sidebar-border p-2">
        {rail ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex justify-center py-1">
                <UserAvatar name={profile?.full_name} className="bg-white/15 text-white" />
              </div>
            </TooltipTrigger>
            <TooltipContent side="right">
              {profile?.full_name} · {roleLabel(profile?.role)}
            </TooltipContent>
          </Tooltip>
        ) : (
          <div className="flex items-center gap-3 px-3 py-2">
            <UserAvatar name={profile?.full_name} className="bg-white/15 text-white" />
            <div className="min-w-0 leading-tight">
              <p className="truncate text-sm font-medium text-white">{profile?.full_name}</p>
              <p className="truncate text-xs text-sidebar-muted">
                {roleLabel(profile?.role)}
                {profile?.branch_name ? ` · ${profile.branch_name}` : ''}
              </p>
            </div>
          </div>
        )}
        {rail ? (
          <Tooltip>
            <TooltipTrigger asChild>{signOutButton}</TooltipTrigger>
            <TooltipContent side="right">Sign out</TooltipContent>
          </Tooltip>
        ) : (
          signOutButton
        )}
      </div>
    </div>
  )
}

/** Fixed sidebar for tablet and desktop. Width: 16rem expanded, 4rem rail. */
export function AppSidebar({ rail }: { rail: boolean }) {
  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-30 border-r border-sidebar-border bg-gradient-to-b from-sidebar to-[#0f2d52] text-sidebar-foreground transition-[width] duration-200 motion-reduce:transition-none',
        rail ? 'w-[var(--sidebar-rail-width)]' : 'w-[var(--sidebar-width)]',
      )}
    >
      <SidebarContent rail={rail} />
    </aside>
  )
}
