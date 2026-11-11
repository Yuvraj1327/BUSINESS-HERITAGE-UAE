import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/services/tasks.service'

/** A task change can create, move or resolve alerts and changes the dashboard's Needs Attention counts. */
function useInvalidateTasks() {
  const qc = useQueryClient()
  return () =>
    Promise.all(
      ['tasks', 'alerts', 'dashboard'].map((k) => qc.invalidateQueries({ queryKey: [k] })),
    )
}
const q = { meta: { silent: true } } as const

export const useTaskSummary = () =>
  useQuery({ queryKey: ['tasks', 'summary'], queryFn: api.getTaskSummary, ...q })
export const useAssignees = () =>
  useQuery({ queryKey: ['tasks', 'assignees'], queryFn: api.listAssignees, ...q })
export const useTasks = (f: api.TaskFilters) =>
  useQuery({
    queryKey: ['tasks', 'list', f],
    queryFn: () => api.listTasks(f),
    placeholderData: keepPreviousData,
    ...q,
  })
export const useTask = (id: string) =>
  useQuery({ queryKey: ['tasks', 'detail', id], queryFn: () => api.getTask(id), ...q })

function useTaskMutation<V, R>(fn: (v: V) => Promise<R>) {
  const invalidate = useInvalidateTasks()
  return useMutation({ mutationFn: fn, meta: { silent: true }, onSuccess: invalidate })
}
export const useCreateTask = () => useTaskMutation(api.createTask)
export const useUpdateTask = () =>
  useTaskMutation((v: { id: string; body: api.TaskUpdatePayload }) => api.updateTask(v.id, v.body))
export const useSetTaskStatus = () =>
  useTaskMutation((v: { id: string; status: 'To Do' | 'In Progress' | 'Done'; note?: string }) =>
    api.setTaskStatus(v.id, { status: v.status, ...(v.note ? { note: v.note } : {}) }),
  )
