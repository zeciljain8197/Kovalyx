import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { Sidebar } from '@/components/layout/Sidebar'
import { Navbar } from '@/components/layout/Navbar'
import { NO_FLASH_THEME_SCRIPT } from '@/lib/theme'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'Kovalyx — Retail Analytics',
  description: 'Open-source real-time retail analytics pipeline',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // suppressHydrationWarning: the no-FOUC script below mutates this
  // element's class before React hydrates, so server and client markup
  // intentionally differ here — that's the fix, not a bug.
  return (
    <html lang="en" className={`dark ${inter.variable}`} suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body>
        <div className="flex h-screen">
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <Navbar />
            <main className="flex-1 overflow-y-auto bg-gray-50 p-6 dark:bg-gray-950">{children}</main>
          </div>
        </div>
      </body>
    </html>
  )
}
