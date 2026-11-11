import { z } from 'zod'
import { auditEntrySchema } from '@/schemas/finance'

/* ---------- API responses. Timing (overdue / due today / upcoming) is calculated by the server on the Dubai date. ---------- */
export const TASK_STATUSES = ['To Do', 'In Progress', 'Done'] as const
export type TaskStatus = (typeof TASK_STATUSES)[number]
export const timingSchema = z.enum(['overdue', 'due_today', 'upcoming', 'no_due_date', 'completed'])
export type TaskTiming = z.infer<typeof timingSchema>

export const taskSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  branch_id: z.string().nullable(),
  branch_name: z.string(),
  assignee_id: z.string().nullable(),
  assignee_name: z.string(),
  due_date: z.string().nullable(),
  status: z.enum(TASK_STATUSES),
  timing: timingSchema,
  days_to_due: z.number().nullable(),
  notes: z.string().nullable(),
  created_at: z.string(),
  created_by_name: z.string().nullable(),
  updated_at: z.string(),
  updated_by_name: z.string().nullable(),
  completed_at: z.string().nullable(),
  completed_by_name: z.string().nullable(),
})
export type Task = z.infer<typeof taskSchema>

export const taskPageSchema = z.object({
  items: z.array(taskSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
})
export const taskDetailSchema = z.object({ task: taskSchema, history: z.array(auditEntrySchema) })
export type TaskDetail = z.infer<typeof taskDetailSchema>

export const taskSummarySchema = z.object({
  total: z.number(),
  to_do: z.number(),
  in_progress: z.number(),
  done: z.number(),
  overdue: z.number(),
  due_today: z.number(),
  due_7: z.number(),
})
export type TaskSummary = z.infer<typeof taskSummarySchema>

export const assigneeSchema = z.object({
  id: z.string(),
  name: z.string(),
  role: z.string(),
  branch_name: z.string().nullable(),
})
export type Assignee = z.infer<typeof assigneeSchema>

/* ---------- form ---------- */
export const taskFormSchema = z.object({
  title: z.string().trim().min(1, 'Enter a title').max(200),
  description: z.string().trim().max(2000),
  branch_id: z.string(), // '' = All Branches
  due_date: z.string(),
  assignee_id: z.string(), // '' = Unassigned
  notes: z.string().trim().max(2000),
  reason: z.string().trim().max(500),
})
export type TaskFormInput = z.infer<typeof taskFormSchema>
