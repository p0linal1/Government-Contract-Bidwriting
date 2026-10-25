import { createContext, useContext, useEffect, useState } from 'react'

const STORAGE_KEY = 'cadocary-look-v2'

export const THEMES = [
  { id: 'clean', name: 'Clean', note: 'Soft and factual. Rounded type, closest to TurboTax.', bg: '#f7f7f5' },
  { id: 'ledger', name: 'Ledger', note: 'Black and white, square edges, one orange signal. Swiss and newspaper-like.', bg: '#ffffff' },
  { id: 'memo', name: 'Memo', note: 'Serif headlines on warm paper. Reads like a research report.', bg: '#f5f4f0' },
  { id: 'night', name: 'Night', note: 'Dark, with amber. A pro tool for late-night bid work.', bg: '#121417' },
  { id: 'friendly', name: 'Friendly', note: 'Bright, rounded, cobalt blue. Closest to TurboTax and Lemonade.', bg: '#f3f5fa' },
  { id: 'field', name: 'Field notes', note: 'Graph paper, typewriter headings, olive. An analyst\'s notebook.', bg: '#f2f1ea' },
]

function readSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return THEMES.some((t) => t.id === saved) ? saved : 'clean'
  } catch {
    return 'clean'
  }
}

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readSaved)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEMES.find((t) => t.id === theme).bg)
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // Storage can be blocked. The look still applies for this visit.
    }
  }, [theme])

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}
