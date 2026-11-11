import { z } from 'zod'
import { strongPassword } from '@/schemas/auth'

export const PHONE_PATTERN = /^\+?[0-9 ()-]{7,20}$/

export const profileFormSchema = z.object({
  full_name: z
    .string()
    .trim()
    .min(1, 'Enter your full name')
    .max(150, 'Use at most 150 characters'),
  phone: z
    .string()
    .trim()
    .refine(
      (v) => v === '' || PHONE_PATTERN.test(v),
      'Enter a valid phone number (e.g. +971 50 123 4567)',
    ),
})
export type ProfileFormValues = z.infer<typeof profileFormSchema>

export const changePasswordSchema = z
  .object({
    current: z.string().min(1, 'Enter your current password'),
    password: strongPassword,
    confirm: z.string().min(1, 'Confirm your new password'),
  })
  .refine((v) => v.password === v.confirm, { path: ['confirm'], message: 'Passwords do not match' })
  .refine((v) => v.password !== v.current, {
    path: ['password'],
    message: 'The new password must differ from the current one',
  })
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>

export const changeEmailSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'Enter the new email address')
    .pipe(z.email('Enter a valid email address')),
  current: z.string().min(1, 'Enter your current password'),
})
export type ChangeEmailValues = z.infer<typeof changeEmailSchema>

/** Profile photo rules. Supabase Storage enforces the same limits on the bucket. */
export const AVATAR_MAX_BYTES = 2 * 1024 * 1024
export const AVATAR_TYPES = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/webp': 'webp',
} as const
