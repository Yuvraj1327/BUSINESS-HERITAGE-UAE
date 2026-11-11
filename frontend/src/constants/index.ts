export const APP_NAME = 'ALSAFA Heritage Laundry'
export const CURRENCY = 'AED'
/** Business date rules (today, "no future dates") use Dubai time, matching the database. */
export const BUSINESS_TIMEZONE = 'Asia/Dubai'
export const BANKS = ['ENBD', 'ADCB'] as const
export type Bank = (typeof BANKS)[number]
export const ROLES = ['owner', 'branch'] as const
export type Role = (typeof ROLES)[number]
export const APP_DISPLAY_NAME = 'ALSAFA Heritage Laundry ERP'
