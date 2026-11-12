import { apiClient } from '@/lib/api-client'
import {
  branchDateViewSchema,
  ownerDashboardSchema,
  type BranchDateView,
  type OwnerDashboard,
} from '@/schemas/dashboard'

export type DashboardPreset =
  'today' | 'yesterday' | 'last7' | 'last30' | 'this_month' | 'last_month'

/** `range` mode: either a quick `preset` (resolved on the server in Dubai time) or explicit dates. */
export interface OwnerDashboardParams {
  mode: 'day' | 'month' | 'range'
  date?: string
  month?: string
  preset?: DashboardPreset
  date_from?: string
  date_to?: string
}

export async function getOwnerDashboard(params: OwnerDashboardParams): Promise<OwnerDashboard> {
  const { data } = await apiClient.get<unknown>('/dashboard/owner', { params })
  return ownerDashboardSchema.parse(data)
}

export interface BranchDateParams {
  branch_id?: string
  date_from: string
  date_to: string
}

export async function getBranchDateView(params: BranchDateParams): Promise<BranchDateView> {
  const { data } = await apiClient.get<unknown>('/branch-date-view', { params })
  return branchDateViewSchema.parse(data)
}
