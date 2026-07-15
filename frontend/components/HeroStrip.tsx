'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowRight, X } from 'lucide-react'
import { TechStackStrip } from '@/components/TechStackStrip'

const HERO_DISMISSED_KEY = 'kovalyx-hero-dismissed'

export function HeroStrip() {
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    setDismissed(localStorage.getItem(HERO_DISMISSED_KEY) === 'true')
  }, [])

  if (dismissed) return null

  function dismiss() {
    localStorage.setItem(HERO_DISMISSED_KEY, 'true')
    setDismissed(true)
  }

  return (
    <div className="relative rounded-lg border border-gray-200 bg-gradient-to-br from-gray-50 to-white p-5 dark:border-gray-800 dark:from-gray-900 dark:to-gray-950">
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss"
        className="absolute right-3 top-3 text-gray-400 hover:text-gray-600 dark:text-gray-600 dark:hover:text-gray-300"
      >
        <X size={16} />
      </button>
      <p className="max-w-3xl text-sm text-gray-700 dark:text-gray-300">
        Kovalyx is a self-hosted, real-time retail analytics pipeline — Kafka streams events through a
        Bronze/Silver/Gold medallion architecture, masking PII and enforcing data-quality gates before any
        number reaches this dashboard. Every KPI below is queried live from that governed Gold layer.
      </p>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <TechStackStrip />
        <Link
          href="/about"
          className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-kovalyx-goldText hover:underline dark:text-kovalyx-gold"
        >
          How it works <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  )
}
