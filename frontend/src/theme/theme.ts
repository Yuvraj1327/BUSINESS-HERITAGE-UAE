import type { ThemeChoice } from '@/schemas/preferences'

/** Device-local copy of the choice so the right theme is applied before the profile loads (and on /login). */
export const THEME_STORAGE_KEY = 'alsafa-theme'

export function readStoredTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY)
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function storeTheme(choice: ThemeChoice) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, choice)
  } catch {
    /* private mode: the profile copy still persists the choice */
  }
}

export function systemPrefersDark(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

export function resolveTheme(choice: ThemeChoice): 'light' | 'dark' {
  return choice === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : choice
}

/** Toggles the `dark` class (see globals.css) and the browser colour scheme. */
export function applyTheme(choice: ThemeChoice) {
  const resolved = resolveTheme(choice)
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.style.colorScheme = resolved
}
