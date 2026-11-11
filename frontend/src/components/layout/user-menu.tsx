import { ChevronDown, LogOut } from 'lucide-react'
import { useAuth } from '@/auth/use-auth'
import { UserAvatar } from '@/components/layout/user-avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { roleLabel } from '@/utils/user'

/** Avatar, name and role in the header, with a dropdown showing the account and the sign-out action. */
export function UserMenu() {
  const { profile, signOut } = useAuth()
  if (!profile) return null
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Account menu for ${profile.full_name}`}
        className="flex min-h-11 items-center gap-2 rounded-md px-1.5 hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring md:min-h-10"
      >
        <UserAvatar name={profile.full_name} />
        <span className="hidden min-w-0 text-left leading-tight lg:block">
          <span className="block max-w-40 truncate text-sm font-medium">{profile.full_name}</span>
          <span className="block text-xs text-muted-foreground">{roleLabel(profile.role)}</span>
        </span>
        <ChevronDown className="hidden size-4 text-muted-foreground lg:block" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>
          <span className="block truncate font-semibold">{profile.full_name}</span>
          <span className="block text-xs font-normal text-muted-foreground">
            {roleLabel(profile.role)}
            {profile.branch_name ? ` · ${profile.branch_name}` : ' · All branches'}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOut aria-hidden /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
