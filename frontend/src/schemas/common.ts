import { z } from 'zod'

/** Money travels as a decimal string (NUMERIC(14,2) in the database): up to 12 integer digits, 2 decimals. */
export const aedAmountSchema = z
  .string()
  .regex(/^\d{1,12}(\.\d{1,2})?$/, 'Enter a valid amount (max 2 decimals)')

/** Business dates are plain YYYY-MM-DD strings. */
export const isoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Use YYYY-MM-DD')
