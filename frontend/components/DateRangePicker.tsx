'use client'

import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { clsx } from 'clsx'
import { RANGE_PRESETS, parseRangeParam } from '@/lib/dateRange'

export function DateRangePicker() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const current = parseRangeParam(searchParams.get('range') ?? undefined)

  function setRange(value: string) {
    const params = new URLSearchParams(searchParams.toString())
    params.set('range', value)
    // typedRoutes can't type-check a dynamic template literal against the
    // generated route list — this is a same-page query-param update, not
    // a route change, so the runtime path is always valid regardless.
    router.push(`${pathname}?${params.toString()}` as Parameters<typeof router.push>[0])
  }

  return (
    <div className="flex gap-1">
      {RANGE_PRESETS.map((preset) => (
        <button
          key={preset.value}
          type="button"
          onClick={() => setRange(preset.value)}
          className={clsx(
            'rounded-md px-3 py-1.5 text-xs font-medium',
            current === preset.value
              ? 'bg-kovalyx-goldText text-white dark:bg-kovalyx-gold dark:text-gray-950'
              : 'bg-gray-100 text-gray-500 hover:text-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:text-gray-200'
          )}
        >
          {preset.label}
        </button>
      ))}
    </div>
  )
}
