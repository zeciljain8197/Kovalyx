'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { clsx } from 'clsx'
import { BarChart2, Users, Package, RotateCcw, Activity, Info, LucideIcon } from 'lucide-react'

interface NavItem {
  href: '/' | '/customers' | '/inventory' | '/returns' | '/pipeline' | '/about'
  label: string
  icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { href: '/', label: 'Sales Overview', icon: BarChart2 },
  { href: '/customers', label: 'Customer Intelligence', icon: Users },
  { href: '/inventory', label: 'Inventory Alerts', icon: Package },
  { href: '/returns', label: 'Returns Analysis', icon: RotateCcw },
  { href: '/pipeline', label: 'Pipeline Health', icon: Activity },
  { href: '/about', label: 'About This Project', icon: Info },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <div className="flex h-16 items-center px-6">
        <span className="text-xl font-bold text-kovalyx-goldText dark:text-kovalyx-gold">Kovalyx</span>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href
          const Icon = item.icon
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-kovalyx-goldText/10 text-kovalyx-goldText dark:bg-kovalyx-gold/10 dark:text-kovalyx-gold'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-200'
              )}
            >
              <Icon size={16} />
              <span className="flex-1">{item.label}</span>
            </Link>
          )
        })}
      </nav>
      <div className="border-t border-gray-200 px-4 py-4 text-xs text-gray-500 dark:border-gray-800">
        <div>
          Powered by{' '}
          <a
            href="https://github.com/zeciljain8197/Kovalyx"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-500 hover:text-kovalyx-goldText dark:text-gray-400 dark:hover:text-kovalyx-gold"
          >
            Kovalyx
          </a>
        </div>
        <div className="mt-1 text-gray-400 dark:text-gray-600">v1.0.0</div>
      </div>
    </aside>
  )
}
