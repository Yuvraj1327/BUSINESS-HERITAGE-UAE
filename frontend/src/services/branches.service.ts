import { apiClient } from '@/lib/api-client'
import { branchListSchema, type Branch } from '@/schemas/branch'

export async function listBranches(): Promise<Branch[]> {
  const { data } = await apiClient.get<unknown>('/branches')
  return branchListSchema.parse(data)
}
