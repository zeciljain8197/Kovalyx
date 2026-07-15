'use client'

import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { THEME_STORAGE_KEY } from '@/lib/theme'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Sales Overview',
  '/customers': 'Customer Intelligence',
  '/inventory': 'Inventory Alerts',
  '/returns': 'Returns Analysis',
  '/pipeline': 'Pipeline Health',
  '/about': 'About This Project',
}

export function Navbar() {
  const pathname = usePathname()
  const [isDark, setIsDark] = useState(true)

  useEffect(() => {
    setIsDark(document.documentElement.classList.contains('dark'))
  }, [])

  function toggleDarkMode() {
    const next = !isDark
    setIsDark(next)
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem(THEME_STORAGE_KEY, next ? 'dark' : 'light')
  }

  const title = PAGE_TITLES[pathname] ?? 'Kovalyx'

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6 dark:border-gray-800 dark:bg-gray-950">
      <div className="flex items-center gap-4">
        <span className="text-lg font-bold text-kovalyx-goldText dark:text-kovalyx-gold">Kovalyx</span>
        <span className="text-gray-300 dark:text-gray-600">/</span>
        <span className="text-sm text-gray-600 dark:text-gray-300">{title}</span>
      </div>
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={toggleDarkMode}
          aria-label="Toggle dark mode"
          className="rounded-full p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-200"
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  )
}
