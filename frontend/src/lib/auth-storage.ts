/**
 * Where Supabase keeps the session in the browser.
 * "Keep me signed in" ON  -> localStorage (survives closing the browser).
 * "Keep me signed in" OFF -> sessionStorage (ends when the tab/browser closes).
 * The choice is a non-sensitive flag stored under REMEMBER_KEY. Reads check both stores so a session is always found.
 */
export const REMEMBER_KEY = 'alsafa-auth-remember'

function safe<T>(fn: () => T, fallback: T): T {
  try {
    return fn()
  } catch {
    return fallback // storage can be blocked (private mode / policy); auth then simply does not persist
  }
}

export function setRememberSession(remember: boolean) {
  safe(() => localStorage.setItem(REMEMBER_KEY, remember ? '1' : '0'), undefined)
}

export function getRememberSession(): boolean {
  return safe(() => localStorage.getItem(REMEMBER_KEY) !== '0', true)
}

export const authStorage = {
  getItem(key: string): string | null {
    return (
      safe(() => sessionStorage.getItem(key), null) ?? safe(() => localStorage.getItem(key), null)
    )
  },
  setItem(key: string, value: string) {
    const [target, other] = getRememberSession()
      ? [localStorage, sessionStorage]
      : [sessionStorage, localStorage]
    safe(() => target.setItem(key, value), undefined)
    safe(() => other.removeItem(key), undefined)
  },
  removeItem(key: string) {
    safe(() => sessionStorage.removeItem(key), undefined)
    safe(() => localStorage.removeItem(key), undefined)
  },
}
