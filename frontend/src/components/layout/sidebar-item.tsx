import type { LucideIcon } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { sidebarItemClass } from '@/components/layout/sidebar-styles'
import { cn } from '@/lib/utils'

interface SidebarItemProps {
  to: string
  label: string
  icon: LucideIcon
  /** Icon-only rail: the label stays available to screen readers and as a tooltip. */
  rail?: boolean
  indent?: boolean
  onNavigate?: () => void
}

/** One navigation link. Active state comes from the router, not from local state. */
export function SidebarItem({
  to,
  label,
  icon: Icon,
  rail = false,
  indent = false,
  onNavigate,
}: SidebarItemProps) {
  // The active state is computed here and passed as a plain string: when this link sits inside a Radix
  // `asChild` trigger (tooltip), Slot would stringify a NavLink className *function* and drop all styling.
  const { pathname } = useLocation()
  const active = to === '/' ? pathname === '/' : pathname === to || pathname.startsWith(`${to}/`)
  const link = (
    <NavLink
      to={to}
      end={to === '/'}
      onClick={onNavigate}
      className={cn(sidebarItemClass(active, rail), indent && !rail && 'pl-10')}
    >
      {indent && !rail ? null : <Icon className="size-[18px] shrink-0" aria-hidden />}
      <span className={cn('truncate', rail && 'sr-only')}>{label}</span>
    </NavLink>
  )
  if (!rail) return link
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  )
}
