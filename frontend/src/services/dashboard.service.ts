import { apiClient } from '@/lib/api-client'
import {
  branchDateViewSchema,
  ownerDashboardSchema,
  type BranchDateView,
  type OwnerDashboard,
} from '@/schemas/dashboard'

export interface OwnerDashboardParams {
  mode: 'day' | 'month'
  date?: string
  month?: string
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
