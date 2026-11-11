import { createContext, useContext } from 'react'
import type { Branch } from '@/schemas/branch'

export const ALL_BRANCHES = 'all' as const

export interface BranchContextValue {
  /** True when the user may pick a branch (scope all_branches). Branch Users never can. */
  canChoose: boolean
  /** 'all' (every branch) or one branch id. For a Branch User always their own branch id. */
  selectedBranchId: string
  selectedBranchName: string | null
  setSelectedBranchId: (id: string) => void
  branches: Branch[]
  branchesStatus: 'loading' | 'error' | 'ready' | 'idle'
}

export const BranchContext = createContext<BranchContextValue | null>(null)

export function useBranchContext(): BranchContextValue {
  const ctx = useContext(BranchContext)
  if (!ctx) throw new Error('useBranchContext must be used inside an Owner or Branch layout')
  return ctx
}
