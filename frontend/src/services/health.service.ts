import { apiClient } from '@/lib/api-client'
import { healthSchema, readinessSchema, type Health, type Readiness } from '@/schemas/health'

export async function getHealth(): Promise<Health> {
  const { data } = await apiClient.get<unknown>('/health')
  return healthSchema.parse(data)
}

export async function getReadiness(): Promise<Readiness> {
  const { data } = await apiClient.get<unknown>('/health/ready')
  return readinessSchema.parse(data)
}
