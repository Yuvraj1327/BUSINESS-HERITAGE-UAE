import { cn } from '@/lib/utils'

/** Shared look of a sidebar row (link or group header). */
export const sidebarItemClass = (active: boolean, rail: boolean) =>
  cn(
    'flex min-h-11 items-center gap-3 rounded-md px-3 text-sm md:min-h-9 transition-colors focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-white',
    rail && 'justify-center px-0',
    active
      ? 'bg-sidebar-accent font-medium text-white'
      : 'text-sidebar-foreground hover:bg-sidebar-accent/70 hover:text-white',
  )
