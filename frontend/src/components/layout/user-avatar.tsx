import { initials } from '@/utils/user'
import { cn } from '@/lib/utils'

/** Initials by default; shows the user's photo when a (signed) URL is given. Decorative: the name is next to it. */
export function UserAvatar({
  name,
  src,
  className,
}: {
  name: string | null | undefined
  src?: string | null
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn(
        'grid size-9 shrink-0 place-items-center overflow-hidden rounded-full bg-secondary text-xs font-semibold text-primary',
        className,
      )}
    >
      {src ? (
        <img src={src} alt="" className="size-full object-cover" referrerPolicy="no-referrer" />
      ) : (
        initials(name)
      )}
    </span>
  )
}
