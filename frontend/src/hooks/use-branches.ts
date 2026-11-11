import { useQuery } from '@tanstack/react-query'
import { listBranches } from '@/services/branches.service'

export function useBranches(enabled = true) {
  return useQuery({
    queryKey: ['branches'],
    queryFn: listBranches,
    enabled,
    meta: { silent: true }, // the selector shows its own "unavailable" state
    staleTime: 5 * 60_000,
    retry: 1,
  })
}
