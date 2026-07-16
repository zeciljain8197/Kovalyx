'use client'

import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import Image from 'next/image'
import { Menu, Moon, Sun } from 'lucide-react'
import { THEME_STORAGE_KEY } from '@/lib/theme'
import { useMobileNav } from '@/lib/mobile-nav'

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
  const { toggle } = useMobileNav()
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
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4 dark:border-gray-800 dark:bg-gray-950 sm:px-6">
      <div className="flex min-w-0 items-center gap-4">
        <button
          type="button"
          onClick={toggle}
          aria-label="Open menu"
          className="shrink-0 rounded-md p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-200 lg:hidden"
        >
          <Menu size={20} />
        </button>
        <div className="shrink-0 lg:hidden">
          <Image src="/logo_light_theme.png" alt="" width={26} height={26} className="rounded dark:hidden" />
          <Image src="/logo_dark_theme.png" alt="" width={26} height={26} className="hidden rounded dark:block" />
        </div>
        <span className="shrink-0 text-lg font-bold text-kovalyx-goldText dark:text-kovalyx-gold">Kovalyx</span>
        <span className="hidden text-gray-300 dark:text-gray-600 sm:inline">/</span>
        <span className="hidden truncate text-sm text-gray-600 dark:text-gray-300 sm:inline">{title}</span>
      </div>
      <div className="flex shrink-0 items-center gap-4">
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
