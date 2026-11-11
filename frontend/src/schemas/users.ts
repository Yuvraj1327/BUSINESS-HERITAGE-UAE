import { z } from 'zod'
import { strongPassword } from '@/schemas/auth'

/** GET/POST /api/v1/users (Owner only): profile rows. No email, no tokens. */
export const userSchema = z.object({
  user_id: z.string(),
  full_name: z.string(),
  role: z.string(),
  branch_id: z.string().nullable(),
  is_active: z.boolean(),
  created_at: z.string(),
})
export type UserProfile = z.infer<typeof userSchema>
export const userListSchema = z.array(userSchema)

/** Owner creates a Branch User. There is no role field: the server always creates role "branch". */
export const userCreateSchema = z
  .object({
    email: z.string().trim().min(1, 'Enter an email address').email('Enter a valid email address'),
    full_name: z.string().trim().min(1, 'Enter the full name').max(150),
    branch_id: z.string().min(1, 'Choose a branch'),
    /** Initial password chosen by the Owner. Held in memory only; the user must change it on first login. */
    password: strongPassword,
    confirm_password: z.string().min(1, 'Confirm the password'),
  })
  .refine((v) => v.password === v.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  })
  .refine(
    (v) => {
      const local = (v.email.split('@')[0] ?? '').toLowerCase()
      return local.length < 4 || !v.password.toLowerCase().includes(local)
    },
    { path: ['password'], message: 'Must not contain the email address' },
  )
export type UserCreateValues = z.infer<typeof userCreateSchema>
