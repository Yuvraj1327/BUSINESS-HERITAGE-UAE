import { useMutation, useQuery } from '@tanstack/react-query'
import { useAuth } from '@/auth/use-auth'
import type { Preferences } from '@/schemas/preferences'
import * as api from '@/services/settings.service'

/** Signed URL for the user's private profile photo (cached for most of its one-hour life). */
export function useAvatarUrl(path: string | null | undefined) {
  const q = useQuery({
    queryKey: ['avatar-url', path],
    queryFn: () => api.getAvatarUrl(path!),
    enabled: Boolean(path),
    staleTime: 50 * 60_000,
    meta: { silent: true },
  })
  return path ? (q.data ?? null) : null
}

export function useUpdateProfile() {
  const { applyProfile } = useAuth()
  return useMutation({
    mutationFn: api.updateOwnProfile,
    onSuccess: applyProfile,
  })
}

export function useSavePreferences() {
  const { applyProfile } = useAuth()
  return useMutation({
    mutationFn: (p: Preferences) => api.saveOwnPreferences(p),
    onSuccess: applyProfile,
  })
}
