import type { UserProfile } from '@/schemas/auth'

/** Mirrors the backend enums (backend/app/core/permissions.py). Values only; the RULES come from the server. */
export const MODULES = [
  'dashboard',
  'branch_management',
  'daily_reports',
  'cash_banks',
  'opening_balances',
  'expenses',
  'suppliers',
  'employees',
  'visas_passports',
  'trade_licenses',
  'rentals_cheques',
  'tasks',
  'reports',
  'user_management',
  'settings',
  'audit_log',
] as const
export type AppModule = (typeof MODULES)[number]

export const ACTIONS = [
  'read',
  'create',
  'update',
  'delete',
  'approve',
  'export',
  'manage',
] as const
export type AppAction = (typeof ACTIONS)[number]

export type PermissionMap = UserProfile['permissions']

/** Default deny: anything not explicitly granted by the server is false. For display decisions only. */
export function hasPermission(
  permissions: PermissionMap | null | undefined,
  module: AppModule,
  action: AppAction,
): boolean {
  return permissions?.[module]?.actions.includes(action) ?? false
}

export function scopeOf(
  permissions: PermissionMap | null | undefined,
  module: AppModule,
): 'all_branches' | 'own_branch' | null {
  return permissions?.[module]?.scope ?? null
}
