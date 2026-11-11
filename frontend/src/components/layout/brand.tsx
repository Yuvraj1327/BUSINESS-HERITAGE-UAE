import { APP_NAME } from '@/constants'
import { cn } from '@/lib/utils'

/**
 * ALSAFA logo + wordmark. The logo artwork has a white background, so on dark surfaces (`light`) it sits on a
 * white rounded tile. `stacked` is the large centered lockup used on the sign-in pages.
 */
export function Brand({
  className,
  light = false,
  compact = false,
  stacked = false,
  compactText = false,
}: {
  className?: string
  /** Rendered on a dark surface (sidebar, sign-in backdrop). */
  light?: boolean
  /** Logo mark only (icon rail). The name stays available to screen readers. */
  compact?: boolean
  /** Large vertical lockup: logo above the name. */
  stacked?: boolean
  /** Smaller lockup for the phone header. */
  compactText?: boolean
}) {
  const subtitle = APP_NAME.replace('ALSAFA ', '')
  return (
    <div
      className={cn('flex items-center gap-3', stacked && 'flex-col gap-4 text-center', className)}
    >
      <span
        className={cn(
          'grid shrink-0 place-items-center overflow-hidden bg-white shadow-sm ring-1',
          light ? 'ring-white/20' : 'ring-border',
          stacked
            ? 'size-44 rounded-full shadow-lg sm:size-52'
            : compactText
              ? 'size-9 rounded-lg p-0.5'
              : 'size-10 rounded-xl p-0.5',
        )}
      >
        <img
          src="/logo.png"
          alt=""
          width={512}
          height={512}
          className="size-full object-contain"
          draggable={false}
        />
      </span>
      <span className={cn('leading-none', (compact || stacked) && 'sr-only')}>
        <span
          className={cn(
            'block font-bold uppercase',
            stacked
              ? 'text-3xl tracking-[0.28em] sm:text-4xl'
              : compactText
                ? 'text-[15px] tracking-[0.2em]'
                : 'text-[17px] tracking-[0.22em]',
            light ? 'text-white' : 'text-primary',
          )}
        >
          ALSAFA
        </span>
        <span
          className={cn(
            'block font-medium uppercase',
            stacked ? 'mt-2 text-xs tracking-[0.3em]' : 'mt-1 text-[10px] tracking-[0.2em]',
            light ? 'text-sky-200' : 'text-teal',
          )}
        >
          {subtitle}
        </span>
        {stacked ? (
          <span
            className={cn(
              'mx-auto mt-3 block h-0.5 w-12 rounded-full',
              light ? 'bg-sky-300/60' : 'bg-teal/60',
            )}
            aria-hidden
          />
        ) : null}
      </span>
    </div>
  )
}
