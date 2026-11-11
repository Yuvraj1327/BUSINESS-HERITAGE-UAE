import { cn } from '@/lib/utils'

interface SwitchProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  /** Accessible name when no visible label is associated. */
  'aria-label'?: string
  'aria-labelledby'?: string
  disabled?: boolean
  id?: string
}

/** On/off toggle (role="switch"), keyboard operable, 44px touch target on phones. */
export function Switch({ checked, onCheckedChange, disabled, ...aria }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-transparent transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50',
        checked ? 'bg-accent' : 'bg-input',
      )}
      {...aria}
    >
      <span
        aria-hidden
        className={cn(
          'block size-5 rounded-full bg-white shadow transition-transform motion-reduce:transition-none',
          checked ? 'translate-x-5' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}
