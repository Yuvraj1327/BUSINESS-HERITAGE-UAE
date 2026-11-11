import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { usePermissions } from '@/auth/use-permissions'
import {
  ALL_BRANCHES,
  BranchContext,
  type BranchContextValue,
} from '@/components/layout/branch-context'
import { useBranches } from '@/hooks/use-branches'

const STORAGE_KEY = 'alsafa.selectedBranch'

function readStored(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? ALL_BRANCHES
  } catch {
    return ALL_BRANCHES
  }
}

/**
 * Global branch selection for users whose dashboard scope is all branches. The choice is a UI filter only: the
 * API still authorizes every branch id it receives. Users limited to one branch get that branch, fixed, and the
 * branch list is never requested.
 */
export function BranchProvider({ children }: { children: ReactNode }) {
  const { scope, branchId, branchName } = usePermissions()
  const canChoose = scope('dashboard') === 'all_branches'
  const branches = useBranches(canChoose)
  const [stored, setStored] = useState(readStored)

  const setSelectedBranchId = useCallback((id: string) => {
    setStored(id)
    try {
      sessionStorage.setItem(STORAGE_KEY, id)
    } catch {
      /* storage unavailable: the choice just lasts for this page view */
    }
  }, [])

  const value = useMemo<BranchContextValue>(() => {
    const list = canChoose ? (branches.data ?? []) : []
    // A remembered branch that no longer exists falls back to "all".
    const selected = canChoose
      ? stored === ALL_BRANCHES || list.some((b) => b.id === stored)
        ? stored
        : ALL_BRANCHES
      : (branchId ?? ALL_BRANCHES)
    return {
      canChoose,
      selectedBranchId: selected,
      selectedBranchName: canChoose
        ? (list.find((b) => b.id === selected)?.name ?? null)
        : branchName,
      setSelectedBranchId,
      branches: list,
      branchesStatus: !canChoose
        ? 'idle'
        : branches.isPending
          ? 'loading'
          : branches.isError
            ? 'error'
            : 'ready',
    }
  }, [
    canChoose,
    branches.data,
    branches.isPending,
    branches.isError,
    stored,
    branchId,
    branchName,
    setSelectedBranchId,
  ])

  return <BranchContext.Provider value={value}>{children}</BranchContext.Provider>
}
