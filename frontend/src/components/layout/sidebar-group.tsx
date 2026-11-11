import { ChevronDown, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { SidebarItem } from '@/components/layout/sidebar-item'
import { sidebarItemClass } from '@/components/layout/sidebar-styles'
import type { NavItem } from '@/config/navigation'
import { cn } from '@/lib/utils'

interface SidebarGroupProps {
  /** An expandable item (has children). */
  item: NavItem & { icon: LucideIcon }
  rail?: boolean
  onNavigate?: () => void
}

/**
 * Expandable menu group. Open while one of its pages is active (until the user closes it); in the icon rail it
 * collapses to a single link to its first page, because a rail has no room for a submenu.
 */
export function SidebarGroup({ item, rail = false, onNavigate }: SidebarGroupProps) {
  const { pathname } = useLocation()
  const children = item.children ?? []
  const hasActive = children.some(
    (c) => c.to && (pathname === c.to || pathname.startsWith(`${c.to}/`)),
  )
  const [toggled, setToggled] = useState<boolean | null>(null)
  const open = toggled ?? hasActive
  const Icon = item.icon

  if (rail) {
    const first = children[0]
    return first?.to ? (
      <SidebarItem to={first.to} label={item.label} icon={Icon} rail onNavigate={onNavigate} />
    ) : null
  }
  const panelId = `nav-group-${item.key}`
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setToggled(!open)}
        className={cn(sidebarItemClass(false, false), 'w-full text-left')}
      >
        <Icon className="size-[18px] shrink-0" aria-hidden />
        <span className="flex-1 truncate">{item.label}</span>
        <ChevronDown
          className={cn('size-4 shrink-0 transition-transform', open && 'rotate-180')}
          aria-hidden
        />
      </button>
      {open ? (
        <div id={panelId} className="mt-0.5 space-y-0.5">
          {children.map((child) =>
            child.to ? (
              <SidebarItem
                key={child.key}
                to={child.to}
                label={child.label}
                icon={child.icon}
                indent
                onNavigate={onNavigate}
              />
            ) : null,
          )}
        </div>
      ) : null}
    </div>
  )
}
