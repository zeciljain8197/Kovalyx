'use client'

import { useMemo } from 'react'
import { format } from 'date-fns'
import type { CohortRow } from '@/lib/queries/customers'

export interface CohortHeatmapProps {
  data: CohortRow[]
}

const WEEK_COLUMNS = Array.from({ length: 13 }, (_, i) => i) // Week 0 .. Week 12

function cellColor(retentionRate: number): string {
  if (retentionRate >= 0.9) return 'bg-green-500'
  if (retentionRate >= 0.75) return 'bg-green-700'
  if (retentionRate >= 0.5) return 'bg-yellow-600'
  if (retentionRate >= 0.25) return 'bg-orange-700'
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
            <th className="px-2 py-1 text-left text-gray-400">Cohort</th>
            {WEEK_COLUMNS.map((w) => (
              <th key={w} className="px-2 py-1 text-center font-normal text-gray-400">
                Week {w}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cohortWeeks.map((cohortWeek) => (
            <tr key={cohortWeek}>
              <td className="whitespace-nowrap px-2 py-1 text-gray-300">
                {(() => {
                  try {
                    return format(new Date(cohortWeek), 'MMM d, yyyy')
                  } catch {
                    return cohortWeek
                  }
                })()}
              </td>
              {WEEK_COLUMNS.map((w) => {
                const cell = grid.get(cohortWeek)?.get(w)
                if (!cell) {
                  return (
                    <td key={w} className="p-1">
                      <div className="h-8 w-14 rounded bg-gray-800" title="No data yet" />
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
    </div>
  )
}
