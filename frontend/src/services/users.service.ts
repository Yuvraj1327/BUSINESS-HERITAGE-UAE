import { apiClient } from '@/lib/api-client'
import {
  userListSchema,
  userSchema,
  type UserCreateValues,
  type UserProfile,
} from '@/schemas/users'

export async function listUsers(): Promise<UserProfile[]> {
  const { data } = await apiClient.get<unknown>('/users')
  return userListSchema.parse(data)
}

export async function createUser(body: UserCreateValues): Promise<UserProfile> {
  const { data } = await apiClient.post<unknown>('/users', body)
  return userSchema.parse(data)
}
