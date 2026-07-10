import { createContext, type ReactNode, useContext, useEffect, useState } from 'react'

// User preferences that actually take effect + persist (previously the settings dialog was inert):
//   • theme  — light / dark / system; stamps data-theme on <html> so the CSS dark override applies.
//   • density — the decision-card layout (split / brief / dense) the operator defaults to.
// Persisted to localStorage so they survive a refresh. This is a demo preference store, not a
// server-synced profile (a production seam, like the auth session).

type Theme = 'light' | 'dark' | 'system'
export type Density = 'split' | 'brief' | 'dense'

type PrefsState = {
  theme: Theme
  density: Density
  setTheme: (t: Theme) => void
  setDensity: (d: Density) => void
}

const KEY = 'pipeguard.prefs'
const DEFAULTS: { theme: Theme; density: Density } = { theme: 'light', density: 'split' }

function load(): { theme: Theme; density: Density } {
  try {
    return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY) || '{}') as object) }
  } catch {
    return DEFAULTS
  }
}

function resolveTheme(theme: Theme): 'light' | 'dark' {
  if (theme !== 'system') return theme
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const PrefsContext = createContext<PrefsState | null>(null)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => load().theme)
  const [density, setDensityState] = useState<Density>(() => load().density)

  // Apply the resolved theme to <html> whenever it changes.
  useEffect(() => {
    document.documentElement.dataset.theme = resolveTheme(theme)
  }, [theme])

  // Follow the OS theme live while on "system".
  useEffect(() => {
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      document.documentElement.dataset.theme = mq.matches ? 'dark' : 'light'
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  const persist = (next: { theme: Theme; density: Density }) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      // localStorage unavailable (private mode) — the pref just won't survive a refresh.
    }
  }
  const setTheme = (t: Theme) => {
    setThemeState(t)
    persist({ theme: t, density })
  }
  const setDensity = (d: Density) => {
    setDensityState(d)
    persist({ theme, density: d })
  }

  return (
    <PrefsContext.Provider value={{ theme, density, setTheme, setDensity }}>{children}</PrefsContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePrefs(): PrefsState {
  const ctx = useContext(PrefsContext)
  if (!ctx) throw new Error('usePrefs must be used within <PrefsProvider>')
  return ctx
}
