import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { Sidebar } from '@/components/layout/Sidebar'
import { Navbar } from '@/components/layout/Navbar'
import { NO_FLASH_THEME_SCRIPT } from '@/lib/theme'
import { MobileNavProvider } from '@/lib/mobile-nav'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })

const SITE_URL = 'https://kovalyx.vercel.app'
const DESCRIPTION =
  'Self-hosted, real-time retail analytics pipeline — Kafka through PII-safe, governed Gold-layer marts. Live pipeline health, data-quality checks, and KPI dashboards.'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'Kovalyx — Retail Analytics',
    template: '%s · Kovalyx',
  },
  description: DESCRIPTION,
  openGraph: {
    title: 'Kovalyx — Retail Analytics',
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: 'Kovalyx',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Kovalyx — Retail Analytics',
    description: DESCRIPTION,
  },
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
        <MobileNavProvider>
          <div className="flex h-screen">
            <Sidebar />
            <div className="flex flex-1 flex-col overflow-hidden">
              <Navbar />
              <main className="flex-1 overflow-y-auto bg-gray-50 p-6 dark:bg-gray-950">{children}</main>
            </div>
          </div>
        </MobileNavProvider>
      </body>
    </html>
  )
}
