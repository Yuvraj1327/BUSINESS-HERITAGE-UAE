import { z } from 'zod'
import { preferencesSchema } from '@/schemas/preferences'

export const PASSWORD_MIN_LENGTH = 10

const email = z
  .string()
  .trim()
  .min(1, 'Enter your email address')
  .pipe(z.email('Enter a valid email address'))

export const loginSchema = z.object({
  email,
  // No strength rules on login: existing passwords must always be accepted by the form.
  password: z.string().min(1, 'Enter your password'),
  remember: z.boolean(),
})
export type LoginValues = z.infer<typeof loginSchema>

export const forgotPasswordSchema = z.object({ email })
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>

/** Same rules as the backend (app/core/passwords.py); the server re-checks them. */
export const strongPassword = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Use at least ${PASSWORD_MIN_LENGTH} characters`)
  .max(72, 'Use at most 72 characters')
  .regex(/[a-z]/, 'Include a lower case letter')
  .regex(/[A-Z]/, 'Include an upper case letter')
  .regex(/\d/, 'Include at least one number')
  .refine((v) => v === v.trim(), 'Must not start or end with a space')

export const newPasswordSchema = z
  .object({
    password: strongPassword,
    confirmPassword: z.string().min(1, 'Confirm your new password'),
  })
  .refine((v) => v.password === v.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  })
export type NewPasswordValues = z.infer<typeof newPasswordSchema>

export const profileSchema = z.object({
  user_id: z.string(),
  full_name: z.string(),
  role: z.enum(['owner', 'branch']),
  branch_id: z.string().nullable(),
  branch_name: z.string().nullable(),
  is_active: z.boolean(),
  phone: z.string().nullable().default(null),
  /** Key in the private Storage bucket "avatars" (turned into a signed URL in the browser). */
  avatar_path: z.string().nullable().default(null),
  preferences: preferencesSchema.default(() => preferencesSchema.parse({})),
  /** True until the user replaces the Owner-issued initial password (server blocks everything else meanwhile). */
  must_change_password: z.boolean().default(false),
  /** Display hints from the server's central permission matrix. The API re-checks every request. */
  permissions: z.record(
    z.string(),
    z.object({ actions: z.array(z.string()), scope: z.enum(['all_branches', 'own_branch']) }),
  ),
})
export type UserProfile = z.infer<typeof profileSchema>
