import { z } from 'zod'

export const healthSchema = z.object({
  status: z.string(),
  service: z.string(),
  version: z.string(),
  environment: z.string(),
  time: z.string(),
})
export type Health = z.infer<typeof healthSchema>

export const readinessSchema = z.object({
  status: z.string(),
  database: z.string(),
})
export type Readiness = z.infer<typeof readinessSchema>
