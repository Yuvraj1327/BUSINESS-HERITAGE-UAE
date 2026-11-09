import { useMemo } from 'react'
import { usePermissions } from '@/auth/use-permissions'
import { NAV_ITEMS } from '@/config/navigation'

export function useNavigation() {
  const { can } = usePermissions()
  return useMemo(
    () => NAV_ITEMS.filter((item) => item.available && can(item.module, item.action)),
    [can],
  )
}
