import { formatAED } from '@/utils/format'

/** AED amount from a server decimal string, or a dash when there is none. */
export const aed = (v: string | number | null | undefined) =>
  v === null || v === undefined ? '—' : formatAED(String(v))
