import { initials } from '@/utils/user'
import { cn } from '@/lib/utils'

export function UserAvatar({
  name,
  className,
}: {
  name: string | null | undefined
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn(
        'grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold text-primary',
        className,
      )}
    >
      {initials(name)}
    </span>
  )
}
