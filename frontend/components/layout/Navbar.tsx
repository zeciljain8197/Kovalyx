'use client'

import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Sales Overview',
  '/customers': 'Customer Intelligence',
  '/inventory': 'Inventory Alerts',
  '/returns': 'Returns Analysis',
  '/pipeline': 'Pipeline Health',
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
  }

  const title = PAGE_TITLES[pathname] ?? 'Kovalyx'

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-gray-800 bg-gray-950 px-6">
      <div className="flex items-center gap-4">
        <span className="text-lg font-bold text-kovalyx-gold">Kovalyx</span>
        <span className="text-gray-600">/</span>
        <span className="text-sm text-gray-300">{title}</span>
      </div>
      <div className="flex items-center gap-4">
        <a
          href="https://github.com/zeciljain8197/Kovalyx"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-300 hover:border-kovalyx-gold hover:text-kovalyx-gold"
        >
          Live Demo
        </a>
        <button
          type="button"
          onClick={toggleDarkMode}
          aria-label="Toggle dark mode"
          className="rounded-full p-2 text-gray-400 hover:bg-gray-900 hover:text-gray-200"
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  )
}
