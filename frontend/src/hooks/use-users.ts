import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createUser, listUsers } from '@/services/users.service'

export function useUsers() {
  return useQuery({ queryKey: ['users'], queryFn: listUsers, staleTime: 60_000 })
}

export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}
