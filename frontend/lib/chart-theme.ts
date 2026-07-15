'use client'

import { useEffect, useState } from 'react'

export interface ChartTheme {
  grid: string
  axis: string
  tooltipBg: string
  tooltipBorder: string
  tooltipText: string
}

const DARK_THEME: ChartTheme = {
  grid: '#1f2937',
  axis: '#6b7280',
  tooltipBg: '#111827',
  tooltipBorder: '#374151',
  tooltipText: '#f3f4f6',
}

const LIGHT_THEME: ChartTheme = {
  grid: '#e5e7eb',
  axis: '#6b7280',
  tooltipBg: '#ffffff',
  tooltipBorder: '#d1d5db',
  tooltipText: '#111827',
}

/**
 * Recharts takes literal color strings, not Tailwind classes, so the
 * dark:/light rollout can't reach chart chrome (grid lines, axes,
 * tooltips) the way it reaches everything else. This reads the same
 * `dark` class the theme toggle mutates on <html>, via a MutationObserver
 * rather than a React context — simpler given there's exactly one
 * mutation source (Navbar's toggleDarkMode) and no cross-tree state to
 * coordinate. Series/status colors (GMV gold, alert red/yellow/green)
 * are intentionally NOT part of this — they're reserved semantic colors,
 * not surface colors, and stay identical in both themes.
 */
export function useChartTheme(): ChartTheme {
  const [isDark, setIsDark] = useState(true)

  useEffect(() => {
    const root = document.documentElement
    setIsDark(root.classList.contains('dark'))

    const observer = new MutationObserver(() => {
      setIsDark(root.classList.contains('dark'))
    })
    observer.observe(root, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  return isDark ? DARK_THEME : LIGHT_THEME
}
