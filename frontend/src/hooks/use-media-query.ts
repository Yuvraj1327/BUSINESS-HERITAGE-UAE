import { useSyncExternalStore } from 'react'

/** Subscribes to a CSS media query. Where matchMedia does not exist (tests), `fallback` is used. */
export function useMediaQuery(query: string, fallback: boolean): boolean {
  return useSyncExternalStore(
    (notify) => {
      if (typeof window === 'undefined' || !window.matchMedia) return () => undefined
      const mql = window.matchMedia(query)
      mql.addEventListener('change', notify)
      return () => mql.removeEventListener('change', notify)
    },
    () =>
      typeof window !== 'undefined' && window.matchMedia
        ? window.matchMedia(query).matches
        : fallback,
    () => fallback,
  )
}

export type LayoutMode = 'desktop' | 'tablet' | 'mobile'

/** desktop ≥ 1024px (full or collapsed sidebar), tablet 768–1023px (icon rail), mobile < 768px (drawer). */
export function useLayoutMode(): LayoutMode {
  const desktop = useMediaQuery('(min-width: 1024px)', true)
  const tablet = useMediaQuery('(min-width: 768px)', true)
  return desktop ? 'desktop' : tablet ? 'tablet' : 'mobile'
}
