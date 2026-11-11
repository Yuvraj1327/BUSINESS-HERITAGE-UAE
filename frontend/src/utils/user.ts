import type { Role } from '@/constants'

const ROLE_LABELS: Record<Role, string> = { owner: 'Owner', branch: 'Branch User' }

export function roleLabel(role: string | null | undefined): string {
  return role && role in ROLE_LABELS ? ROLE_LABELS[role as Role] : 'User'
}

/** "Test Branch User" → "TB". Falls back to "?" for an empty name. */
export function initials(name: string | null | undefined): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : ''
  return (first + last).toUpperCase()
}
