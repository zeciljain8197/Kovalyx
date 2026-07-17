'use client'

import { useMemo } from 'react'
import type { CohortRow } from '@/lib/queries/customers'

export interface CohortHeatmapProps {
  data: CohortRow[]
}

const WEEK_COLUMNS = Array.from({ length: 13 }, (_, i) => i) // Week 0 .. Week 12

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * `new Date('2026-07-06')` parses as UTC midnight, but date-fns `format`
 * renders in the local timezone — so the server (UTC container) and a
 * client browser in a different timezone can render different calendar
 * dates for the same string, which React flags as a hydration mismatch.
 * Reading the UTC getters instead keeps the rendered date identical
 * regardless of which timezone the code happens to run in.
 */
function formatCohortWeekLabel(dateStr: string): string {
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`
}

/**
 * Thresholds are calibrated to real e-commerce repeat-purchase cohort
 * retention, not SaaS-style day-1 retention (which routinely sits in the
 * 80-95% range). Week-over-week repeat purchase rates in this range —
 * 40%+ strong, single digits by week 10+ — are normal and expected; the
 * previous thresholds required 75%+ for green, which this business's
 * data can never reach (its real ceiling is ~74%), so every cell rendered
 * red or orange regardless of how the cohort actually performed.
 */
function cellColor(retentionRate: number): string {
  if (retentionRate >= 0.4) return 'bg-green-600'
  if (retentionRate >= 0.2) return 'bg-yellow-600'
  if (retentionRate >= 0.1) return 'bg-orange-700'
  return 'bg-red-900'
}

export function CohortHeatmap({ data }: CohortHeatmapProps) {
  const { cohortWeeks, grid } = useMemo(() => {
    const byWeek = new Map<string, Map<number, CohortRow>>()
    for (const row of data) {
      if (!byWeek.has(row.cohort_week)) byWeek.set(row.cohort_week, new Map())
      byWeek.get(row.cohort_week)!.set(row.weeks_since_acquisition, row)
    }
    const weeks = Array.from(byWeek.keys())
      .sort((a, b) => b.localeCompare(a))
      .slice(0, 12)
    return { cohortWeeks: weeks, grid: byWeek }
  }, [data])

  if (cohortWeeks.length === 0) {
    return <p className="text-sm text-gray-500">No cohort data available yet.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-xs">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-gray-500 dark:text-gray-400">Cohort</th>
            {WEEK_COLUMNS.map((w) => (
              <th key={w} className="px-2 py-1 text-center font-normal text-gray-500 dark:text-gray-400">
                Week {w}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cohortWeeks.map((cohortWeek) => (
            <tr key={cohortWeek}>
              <td className="whitespace-nowrap px-2 py-1 text-gray-700 dark:text-gray-300">
                {formatCohortWeekLabel(cohortWeek)}
              </td>
              {WEEK_COLUMNS.map((w) => {
                const cell = grid.get(cohortWeek)?.get(w)
                if (!cell) {
                  return (
                    <td key={w} className="p-1">
                      <div className="h-8 w-14 rounded bg-gray-200 dark:bg-gray-800" title="No data yet" />
                    </td>
                  )
                }
                const pct = Math.round(cell.retention_rate * 100)
                return (
                  <td key={w} className="p-1">
                    <div
                      className={`flex h-8 w-14 items-center justify-center rounded text-[11px] font-medium text-white ${cellColor(cell.retention_rate)}`}
                      title={`${cohortWeek} — Week ${w}: ${cell.active_customers}/${cell.customers_in_cohort} active (${pct}%)`}
                    >
                      {pct}%
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400">
        <span className="font-medium">Retention rate:</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-green-600" /> 40%+</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-yellow-600" /> 20-40%</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-orange-700" /> 10-20%</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-red-900" /> &lt;10%</span>
      </div>
    </div>
  )
}
