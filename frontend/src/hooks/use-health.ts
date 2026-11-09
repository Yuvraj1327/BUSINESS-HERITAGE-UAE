import { useQuery } from '@tanstack/react-query'
import { getHealth } from '@/services/health.service'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    meta: { silent: true }, // shown inline on the status page, not as a toast
    retry: false,
    refetchInterval: 30_000,
  })
}
