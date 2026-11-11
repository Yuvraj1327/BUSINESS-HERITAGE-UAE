import { apiClient } from '@/lib/api-client'
import {
  assigneeSchema,
  taskDetailSchema,
  taskPageSchema,
  taskSummarySchema,
  type TaskStatus,
} from '@/schemas/tasks'
import { z } from 'zod'

type Params = Record<string, string | number | boolean | undefined>
const clean = (p: Params): Params =>
  Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined && v !== ''))

export interface TaskFilters {
  q?: string
  branch_id?: string
  all_branches?: boolean
  status?: TaskStatus
  assignee_id?: string
  unassigned?: boolean
  due_from?: string
  due_to?: string
  view?: 'overdue' | 'today' | 'week' | 'upcoming' | 'open' | 'completed'
  sort: 'due' | 'created' | 'title' | 'status'
  desc: boolean
  page: number
  page_size: number
}
export interface TaskPayload {
  title: string
  description?: string | null
  branch_id: string | null
  due_date?: string | null
  assignee_id: string | null
  notes?: string | null
}
export type TaskUpdatePayload = TaskPayload & { reason?: string }

export const getTaskSummary = async () =>
  taskSummarySchema.parse((await apiClient.get<unknown>('/tasks/summary')).data)
export const listAssignees = async () =>
  z.array(assigneeSchema).parse((await apiClient.get<unknown>('/tasks/assignees')).data)
export const listTasks = async (f: TaskFilters) =>
  taskPageSchema.parse((await apiClient.get<unknown>('/tasks', { params: clean({ ...f }) })).data)
export const getTask = async (id: string) =>
  taskDetailSchema.parse((await apiClient.get<unknown>(`/tasks/${id}`)).data)
export const createTask = async (body: TaskPayload) =>
  taskDetailSchema.parse((await apiClient.post<unknown>('/tasks', body)).data)
export const updateTask = async (id: string, body: TaskUpdatePayload) =>
  taskDetailSchema.parse((await apiClient.put<unknown>(`/tasks/${id}`, body)).data)
export const setTaskStatus = async (id: string, body: { status: TaskStatus; note?: string }) =>
  taskDetailSchema.parse((await apiClient.post<unknown>(`/tasks/${id}/status`, body)).data)
