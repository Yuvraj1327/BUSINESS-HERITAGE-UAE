import { useEffect, type ReactNode } from 'react'
import { useAuth } from '@/auth/use-auth'
import { applyTheme, readStoredTheme, storeTheme } from '@/theme/theme'

/**
 * Keeps the document theme in step with the user's choice. Order of authority: the signed-in user's saved
 * preference (follows them across devices), else this device's stored choice, else the system setting.
 * "System" also follows live changes of the OS setting.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { profile } = useAuth()
  const saved = profile?.preferences.theme
  useEffect(() => {
    const choice = saved ?? readStoredTheme()
    if (saved) storeTheme(saved)
    applyTheme(choice)
    if (choice !== 'system' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyTheme('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [saved])
  return <>{children}</>
}
