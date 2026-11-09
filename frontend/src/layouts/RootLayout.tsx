import { LogOut } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useNavigation } from '@/auth/use-navigation'
import { useAuth } from '@/auth/use-auth'
import { Brand } from '@/components/layout/brand'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Minimal placeholder shell. The full Owner/Branch layout (sidebar, header) arrives in Step 6. */
export function RootLayout() {
  const { profile, signOut } = useAuth()
  const nav = useNavigation()
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b bg-sidebar">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          <Brand light />
          <div className="flex items-center gap-3 text-sidebar-foreground">
            <span className="hidden text-sm sm:inline">{profile?.full_name}</span>
            <Badge variant="secondary" className="uppercase">
              {profile?.role}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              className="text-white hover:bg-white/10 hover:text-white"
              onClick={() => void signOut()}
            >
              <LogOut aria-hidden /> Sign out
            </Button>
          </div>
        </div>
        <nav
          aria-label="Main"
          className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 pb-2 sm:px-6"
        >
          {nav.map((item) => (
            <NavLink
              key={item.key}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-1.5 text-sm whitespace-nowrap text-sidebar-foreground/80 hover:bg-white/10',
                  isActive && 'bg-white/15 font-medium text-white',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t bg-card py-3 text-center text-xs text-muted-foreground">
        ALSAFA Heritage Laundry · Management System
      </footer>
    </div>
  )
}
