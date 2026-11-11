import { z } from 'zod'

/** Mirrors backend/app/schemas/settings.py; the server re-validates everything. */
export const THEMES = ['light', 'dark', 'system'] as const
export type ThemeChoice = (typeof THEMES)[number]

export const DATE_FORMATS = [
  { value: 'dd-mmm-yyyy', label: '12 Nov 2026' },
  { value: 'dd/mm/yyyy', label: '12/11/2026' },
  { value: 'mm/dd/yyyy', label: '11/12/2026' },
  { value: 'yyyy-mm-dd', label: '2026-11-12' },
] as const
export type DateFormatChoice = (typeof DATE_FORMATS)[number]['value']

/** 'Asia/Dubai' is the business timezone. Others only change how timestamps are displayed to this user. */
export const DISPLAY_TIMEZONES = [
  { value: 'Asia/Dubai', label: 'Dubai (UAE business time)' },
  { value: 'device', label: 'This device' },
  { value: 'UTC', label: 'UTC' },
  { value: 'Asia/Kolkata', label: 'India (Asia/Kolkata)' },
  { value: 'Asia/Karachi', label: 'Pakistan (Asia/Karachi)' },
  { value: 'Asia/Manila', label: 'Philippines (Asia/Manila)' },
  { value: 'Europe/London', label: 'London (Europe/London)' },
] as const

export const preferencesSchema = z.object({
  theme: z.enum(THEMES).catch('light'),
  language: z.literal('en').catch('en'),
  date_format: z
    .enum(['dd-mmm-yyyy', 'dd/mm/yyyy', 'mm/dd/yyyy', 'yyyy-mm-dd'])
    .catch('dd-mmm-yyyy'),
  timezone: z
    .string()
    .refine((v) => DISPLAY_TIMEZONES.some((t) => t.value === v))
    .catch('Asia/Dubai'),
  notifications: z
    .object({
      critical: z.boolean().catch(true),
      warning: z.boolean().catch(true),
      info: z.boolean().catch(true),
    })
    .catch({ critical: true, warning: true, info: true }),
})
export type Preferences = z.infer<typeof preferencesSchema>
export const DEFAULT_PREFERENCES: Preferences = preferencesSchema.parse({})
