'use client'

import { useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { Badge } from '@/components/ui/Badge'
import type { InventoryAlert } from '@/lib/queries/inventory'

export interface InventoryStatusTableProps {
  data: InventoryAlert[]
}

type SortColumn = 'alert_level' | 'product_name' | 'days_of_stock_remaining'
type FilterLevel = 'all' | 'red' | 'yellow' | 'green'

const ALERT_SORT_ORDER: Record<string, number> = { red: 1, yellow: 2, green: 3 }

const DOT_CLASSES: Record<string, string> = {
  red: 'bg-red-500',
  yellow: 'bg-yellow-500',
  green: 'bg-green-500',
}

const BADGE_VARIANT: Record<string, 'danger' | 'warning' | 'success'> = {
  red: 'danger',
  yellow: 'warning',
  green: 'success',
}

export function InventoryStatusTable({ data }: InventoryStatusTableProps) {
  const [search, setSearch] = useState('')
  const [filterLevel, setFilterLevel] = useState<FilterLevel>('all')
  const [sortColumn, setSortColumn] = useState<SortColumn>('alert_level')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  function toggleSort(column: SortColumn) {
    if (sortColumn === column) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortColumn(column)
      setSortDir('asc')
    }
  }

  const filtered = useMemo(() => {
    let rows = data
    if (filterLevel !== 'all') rows = rows.filter((r) => r.alert_level === filterLevel)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      rows = rows.filter((r) => r.product_name?.toLowerCase().includes(q))
    }

    const sorted = [...rows].sort((a, b) => {
      let cmp = 0
      if (sortColumn === 'alert_level') {
        cmp = (ALERT_SORT_ORDER[a.alert_level] ?? 4) - (ALERT_SORT_ORDER[b.alert_level] ?? 4)
        if (cmp === 0) {
          const aDays = a.days_of_stock_remaining ?? Infinity
          const bDays = b.days_of_stock_remaining ?? Infinity
          cmp = aDays - bDays
        }
      } else if (sortColumn === 'product_name') {
        cmp = a.product_name.localeCompare(b.product_name)
      } else {
        const aDays = a.days_of_stock_remaining ?? Infinity
        const bDays = b.days_of_stock_remaining ?? Infinity
        cmp = aDays - bDays
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    return sorted
  }, [data, search, filterLevel, sortColumn, sortDir])

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by product name..."
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 placeholder:text-gray-400 focus:border-kovalyx-blueText focus:outline-none dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200 dark:placeholder:text-gray-500 dark:focus:border-kovalyx-blue"
        />
        <div className="flex gap-1">
          {(['all', 'red', 'yellow', 'green'] as FilterLevel[]).map((level) => (
            <button
              key={level}
              type="button"
              onClick={() => setFilterLevel(level)}
              className={clsx(
                'rounded-md px-3 py-1.5 text-xs font-medium capitalize',
                filterLevel === level
                  ? 'bg-kovalyx-blueText text-white dark:bg-kovalyx-blue dark:text-white'
                  : 'bg-gray-100 text-gray-500 hover:text-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:text-gray-200'
              )}
            >
              {level}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
        <table className="min-w-full divide-y divide-gray-200 text-sm dark:divide-gray-800">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="px-4 py-2 text-left font-medium text-gray-500 dark:text-gray-400">Status</th>
              <th
                className="cursor-pointer px-4 py-2 text-left font-medium text-gray-500 dark:text-gray-400"
                onClick={() => toggleSort('product_name')}
              >
                Product Name
              </th>
              <th className="px-4 py-2 text-left font-medium text-gray-500 dark:text-gray-400">Category</th>
              <th className="px-4 py-2 text-right font-medium text-gray-500 dark:text-gray-400">Current Stock</th>
              <th className="px-4 py-2 text-right font-medium text-gray-500 dark:text-gray-400">Reorder Threshold</th>
              <th
                className="cursor-pointer px-4 py-2 text-right font-medium text-gray-500 dark:text-gray-400"
                onClick={() => toggleSort('days_of_stock_remaining')}
              >
                Days of Stock Remaining
              </th>
              <th
                className="cursor-pointer px-4 py-2 text-left font-medium text-gray-500 dark:text-gray-400"
                onClick={() => toggleSort('alert_level')}
              >
                Alert Level
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-800 dark:bg-gray-950">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                  No alerts matching your filters.
                </td>
              </tr>
            ) : (
              filtered.map((row) => (
                <tr key={`${row.product_id}-${row.snapshot_date}`} className="hover:bg-gray-50 dark:hover:bg-gray-900/50">
                  <td className="px-4 py-2">
                    <span className={`inline-block h-2 w-2 rounded-full ${DOT_CLASSES[row.alert_level]}`} />
                  </td>
                  <td className="px-4 py-2 text-gray-700 dark:text-gray-200">{row.product_name}</td>
                  <td className="px-4 py-2 text-gray-500 dark:text-gray-400">{row.category}</td>
                  <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-200">{row.current_stock_level}</td>
                  <td className="px-4 py-2 text-right text-gray-500 dark:text-gray-400">{row.reorder_threshold}</td>
                  <td className="px-4 py-2 text-right text-gray-700 dark:text-gray-200">
                    {row.days_of_stock_remaining !== null ? `${row.days_of_stock_remaining.toFixed(1)} days` : 'N/A'}
                  </td>
                  <td className="px-4 py-2">
                    <Badge variant={BADGE_VARIANT[row.alert_level]}>{row.alert_level}</Badge>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
