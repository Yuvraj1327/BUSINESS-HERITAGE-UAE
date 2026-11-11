import {
  Banknote,
  BarChart3,
  Building2,
  CalendarSearch,
  ClipboardList,
  FileBadge2,
  FileText,
  Landmark,
  LayoutDashboard,
  ListChecks,
  Plane,
  Receipt,
  Settings,
  Truck,
  UserCog,
  Users,
  History,
  Home,
  type LucideIcon,
  Bell,
  ShoppingBag,
} from 'lucide-react'
import type { AppAction, AppModule } from '@/auth/permissions'

export type NavScope = 'all_branches'

export interface NavItem {
  key: string
  label: string
  /** Label shown to users whose grant for the module is limited to their own branch. */
  ownBranchLabel?: string
  icon: LucideIcon
  /** Route. Items with `children` are expandable groups without a route of their own. */
  to?: string
  module: AppModule
  action: AppAction
  /** Only show when the server-sent scope for `module` is this (e.g. cross-branch views). */
  requireScope?: NavScope
  /** 'placeholder' = the route exists and is protected, the module itself is built in a later step. */
  status: 'live' | 'placeholder'
  children?: NavItem[]
}

export interface NavSection {
  key: string
  label: string
  items: NavItem[]
}

/**
 * The one navigation definition. Visibility = the user holds `action` on `module` (server-sent permissions,
 * default deny) and, where given, the required scope. Route guards use the same module/action pairs, so a hidden
 * link is also a blocked URL. No role names appear here on purpose.
 */
export const NAV_SECTIONS: NavSection[] = [
  {
    key: 'overview',
    label: 'Overview',
    items: [
      {
        key: 'dashboard',
        label: 'Dashboard',
        icon: LayoutDashboard,
        to: '/',
        module: 'dashboard',
        action: 'read',
        status: 'live',
      },
    ],
  },
  {
    key: 'operations',
    label: 'Operations',
    items: [
      {
        key: 'branches',
        label: 'Branch Management',
        ownBranchLabel: 'My Branch',
        icon: Building2,
        to: '/branches',
        module: 'branch_management',
        action: 'read',
        status: 'live',
      },
      {
        key: 'branch_date_view',
        label: 'Branch & Date View',
        icon: CalendarSearch,
        to: '/branch-date-view',
        module: 'daily_reports',
        action: 'read',
        status: 'live',
      },
      {
        key: 'daily_reports',
        label: 'Daily Reports',
        icon: FileText,
        to: '/daily-reports',
        module: 'daily_reports',
        action: 'read',
        status: 'live',
      },
    ],
  },
  {
    key: 'orders',
    label: 'Orders & Delivery',
    items: [
      {
        key: 'order_management',
        label: 'Order Management',
        icon: ShoppingBag,
        to: '/order-management',
        module: 'orders',
        action: 'read',
        status: 'live',
      },
      {
        key: 'orders_list',
        label: 'Orders',
        icon: ClipboardList,
        to: '/orders',
        module: 'orders',
        action: 'read',
        status: 'live',
      },
      {
        key: 'customers',
        label: 'Customers',
        icon: Users,
        to: '/customers',
        module: 'customers',
        action: 'read',
        status: 'live',
      },
      {
        key: 'order_operations',
        label: 'Pickup & Delivery',
        icon: Truck,
        to: '/order-operations',
        module: 'orders',
        action: 'read',
        status: 'live',
      },
      {
        key: 'order_reports',
        label: 'Order Reports',
        icon: BarChart3,
        to: '/order-reports',
        module: 'orders',
        action: 'read',
        status: 'live',
      },
    ],
  },
  {
    key: 'finance',
    label: 'Finance',
    items: [
      {
        key: 'cash_banks',
        label: 'Cash & Banks',
        icon: Landmark,
        to: '/cash-banks',
        module: 'cash_banks',
        action: 'read',
        status: 'live',
      },
      {
        key: 'opening_balances',
        label: 'Opening Balances',
        icon: Banknote,
        to: '/opening-balances',
        module: 'opening_balances',
        action: 'read',
        status: 'live',
      },
      {
        key: 'expenses',
        label: 'Expenses & Savings',
        icon: Receipt,
        to: '/expenses',
        module: 'expenses',
        action: 'read',
        status: 'live',
      },
      {
        key: 'suppliers',
        label: 'Suppliers',
        icon: Truck,
        to: '/suppliers',
        module: 'suppliers',
        action: 'read',
        status: 'live',
      },
    ],
  },
  {
    key: 'people',
    label: 'People & Compliance',
    items: [
      {
        key: 'employees',
        label: 'Employees',
        icon: Users,
        to: '/employees',
        module: 'employees',
        action: 'read',
        status: 'live',
      },
      {
        key: 'visas',
        label: 'Visas & Passports',
        icon: Plane,
        to: '/visas-passports',
        module: 'visas_passports',
        action: 'read',
        status: 'live',
      },
      {
        key: 'licenses',
        label: 'Trade Licenses',
        icon: FileBadge2,
        to: '/trade-licenses',
        module: 'trade_licenses',
        action: 'read',
        status: 'live',
      },
    ],
  },
  {
    key: 'property',
    label: 'Property',
    items: [
      {
        key: 'rentals',
        label: 'Rental Agreements',
        icon: Home,
        to: '/rentals',
        module: 'rentals_cheques',
        action: 'read',
        status: 'live',
      },
      {
        key: 'pdc',
        label: 'PDC Cheques',
        icon: Receipt,
        to: '/pdc-cheques',
        module: 'rentals_cheques',
        action: 'read',
        status: 'live',
      },
    ],
  },
  {
    key: 'management',
    label: 'Management',
    items: [
      {
        key: 'tasks',
        label: 'Tasks',
        icon: ListChecks,
        to: '/tasks',
        module: 'tasks',
        action: 'read',
        status: 'live',
      },
      {
        key: 'notifications',
        label: 'Notifications',
        icon: Bell,
        to: '/notifications',
        module: 'alerts',
        action: 'read',
        status: 'live',
      },
      {
        key: 'reports',
        label: 'Reports & Analytics',
        icon: BarChart3,
        to: '/reports',
        module: 'reports',
        action: 'read',
        status: 'live',
      },
      {
        key: 'activity_history',
        label: 'Activity History',
        icon: History,
        to: '/activity-history',
        module: 'audit_log',
        action: 'read',
        status: 'live',
      },
    ],
  },
  {
    key: 'administration',
    label: 'Administration',
    items: [
      {
        key: 'users',
        label: 'User Management',
        icon: UserCog,
        to: '/users',
        module: 'user_management',
        action: 'read',
        status: 'live',
      },
      {
        key: 'settings',
        label: 'Settings',
        icon: Settings,
        module: 'settings',
        action: 'read',
        status: 'live',
        children: [
          {
            key: 'system_status',
            label: 'System status',
            icon: ClipboardList,
            to: '/system-status',
            module: 'settings',
            action: 'read',
            status: 'live',
          },
        ],
      },
    ],
  },
]

/** Pages that exist but are not navigation entries (breadcrumb labels only). */
export const EXTRA_PAGES: Record<string, { section: string; label: string }> = {
  '/more': { section: 'Menu', label: 'More' },
  '/design-system': { section: 'Developer', label: 'Design system' },
}

/** Every routable leaf of the navigation, for building the route table. */
export function navLeaves(sections: NavSection[] = NAV_SECTIONS): NavItem[] {
  return sections.flatMap((s) => s.items.flatMap((i) => (i.children ? i.children : [i])))
}
