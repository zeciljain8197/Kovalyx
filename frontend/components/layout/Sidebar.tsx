'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { clsx } from 'clsx'
import { BarChart2, Users, Package, RotateCcw, Activity, Info, X, LucideIcon } from 'lucide-react'
import { useMobileNav } from '@/lib/mobile-nav'

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
  const { isOpen, close } = useMobileNav()

  return (
    <>
      {/* Backdrop — mobile only, closes the drawer on tap outside it */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={close}
          aria-hidden="true"
        />
      )}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 flex w-60 shrink-0 flex-col border-r border-gray-200 bg-white transition-transform duration-200 dark:border-gray-800 dark:bg-gray-950',
          'lg:static lg:z-auto lg:translate-x-0',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <Image
              src="/logo_light_theme.png"
              alt=""
              width={32}
              height={32}
              className="rounded-md dark:hidden"
            />
            <Image
              src="/logo_dark_theme.png"
              alt=""
              width={32}
              height={32}
              className="hidden rounded-md dark:block"
            />
            <span className="text-xl font-bold text-kovalyx-goldText dark:text-kovalyx-gold">Kovalyx</span>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close menu"
            className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 lg:hidden"
          >
            <X size={20} />
          </button>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-2">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={close}
                className={clsx(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-kovalyx-blueText/10 text-kovalyx-blueText dark:bg-kovalyx-blue/10 dark:text-kovalyx-blue'
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
    </>
  )
}
