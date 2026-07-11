import { createContext, type ReactNode, useContext, useEffect, useState } from 'react'

// User preferences that actually take effect + persist (previously the settings dialog was inert):
//   • theme   — light / dark / system; stamps data-theme on <html> so the CSS dark override applies.
//   • palette — UIC-7 color-theme family; stamps data-palette on <html>, composed with data-theme.
//   • density — the decision-card layout (split / brief / dense) the operator defaults to.
// Persisted to localStorage so they survive a refresh. This is a demo preference store, not a
// server-synced profile (a production seam, like the auth session).

type Theme = 'light' | 'dark' | 'system'
export type Density = 'split' | 'brief' | 'dense'
// UIC-7 — palette FAMILY (a personal pref, off the gate). Each family renders its light complement
// in light mode and its dark complement in dark mode (composed via data-theme × data-palette in
// index.css): clinical→Clinical/Midnight, sand→Sand/Carbon, slate→Slate/Indigo. The id is the
// stable family key; the visible name is theme-dependent (resolved in the settings dialog).
export type Palette = 'clinical' | 'sand' | 'slate'

type PrefsState = {
  theme: Theme
  density: Density
  palette: Palette
  setTheme: (t: Theme) => void
  setDensity: (d: Density) => void
  setPalette: (p: Palette) => void
}

const KEY = 'pipeguard.prefs'
const DEFAULTS: { theme: Theme; density: Density; palette: Palette } = {
  theme: 'light',
  density: 'split',
  palette: 'clinical',
}

function load(): { theme: Theme; density: Density; palette: Palette } {
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
  const [palette, setPaletteState] = useState<Palette>(() => load().palette)

  // Apply the resolved theme to <html> whenever it changes.
  useEffect(() => {
    document.documentElement.dataset.theme = resolveTheme(theme)
  }, [theme])

  // Stamp the palette family on <html>; index.css composes it with data-theme (UIC-7).
  useEffect(() => {
    document.documentElement.dataset.palette = palette
  }, [palette])

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

  const persist = (next: { theme: Theme; density: Density; palette: Palette }) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      // localStorage unavailable (private mode) — the pref just won't survive a refresh.
    }
  }
  const setTheme = (t: Theme) => {
    setThemeState(t)
    persist({ theme: t, density, palette })
  }
  const setDensity = (d: Density) => {
    setDensityState(d)
    persist({ theme, density: d, palette })
  }
  const setPalette = (p: Palette) => {
    setPaletteState(p)
    persist({ theme, density, palette: p })
  }

  return (
    <PrefsContext.Provider value={{ theme, density, palette, setTheme, setDensity, setPalette }}>
      {children}
    </PrefsContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePrefs(): PrefsState {
  const ctx = useContext(PrefsContext)
  if (!ctx) throw new Error('usePrefs must be used within <PrefsProvider>')
  return ctx
}
