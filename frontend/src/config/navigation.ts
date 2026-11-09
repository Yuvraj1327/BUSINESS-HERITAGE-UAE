import type { AppAction, AppModule } from '@/auth/permissions'

export interface NavItem {
  key: string
  label: string
  to: string
  module: AppModule
  action: AppAction
  /** false = module not built yet; hidden for everybody until its step ships. */
  available: boolean
}

/** Single list of navigation entries. Visibility = available AND the user holds the permission. */
export const NAV_ITEMS: NavItem[] = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    to: '/',
    module: 'dashboard',
    action: 'read',
    available: true,
  },
  {
    key: 'daily_reports',
    label: 'Daily reports',
    to: '/daily-reports',
    module: 'daily_reports',
    action: 'read',
    available: false,
  },
  {
    key: 'branches',
    label: 'Branches',
    to: '/branches',
    module: 'branch_management',
    action: 'read',
    available: false,
  },
  {
    key: 'cash_banks',
    label: 'Cash & banks',
    to: '/cash-banks',
    module: 'cash_banks',
    action: 'read',
    available: false,
  },
  {
    key: 'expenses',
    label: 'Expenses',
    to: '/expenses',
    module: 'expenses',
    action: 'read',
    available: false,
  },
  {
    key: 'suppliers',
    label: 'Suppliers',
    to: '/suppliers',
    module: 'suppliers',
    action: 'read',
    available: false,
  },
  {
    key: 'employees',
    label: 'Employees',
    to: '/employees',
    module: 'employees',
    action: 'read',
    available: false,
  },
  {
    key: 'visas',
    label: 'Visas & passports',
    to: '/visas-passports',
    module: 'visas_passports',
    action: 'read',
    available: false,
  },
  {
    key: 'licenses',
    label: 'Trade licences',
    to: '/trade-licenses',
    module: 'trade_licenses',
    action: 'read',
    available: false,
  },
  {
    key: 'rentals',
    label: 'Rentals & cheques',
    to: '/rentals',
    module: 'rentals_cheques',
    action: 'read',
    available: false,
  },
  { key: 'tasks', label: 'Tasks', to: '/tasks', module: 'tasks', action: 'read', available: false },
  {
    key: 'reports',
    label: 'Reports',
    to: '/reports',
    module: 'reports',
    action: 'read',
    available: false,
  },
  {
    key: 'users',
    label: 'Users',
    to: '/users',
    module: 'user_management',
    action: 'read',
    available: false,
  },
  {
    key: 'settings',
    label: 'System status',
    to: '/system-status',
    module: 'settings',
    action: 'read',
    available: true,
  },
]
