import { z } from 'zod'

/** GET /api/v1/branches (Step 5). Branches the caller may see: all for scope all_branches, else their own. */
export const branchSchema = z.object({
  id: z.string(),
  name: z.string(),
  sort_order: z.number(),
  is_active: z.boolean(),
})
export type Branch = z.infer<typeof branchSchema>
export const branchListSchema = z.array(branchSchema)
