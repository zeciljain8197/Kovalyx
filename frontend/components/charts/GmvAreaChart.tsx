'use client'

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { format } from 'date-fns'
import type { DailySales } from '@/lib/queries/sales'
import { useChartTheme } from '@/lib/chart-theme'

export interface GmvAreaChartProps {
  data: DailySales[]
}

function formatGmv(value: number): string {
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`
  return `$${value.toFixed(0)}`
}

function formatDateLabel(dateStr: string): string {
  try {
    return format(new Date(dateStr), 'MMM d')
  } catch {
    return dateStr
  }
}

function GmvTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: DailySales }[]; label?: string }) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0].payload
  return (
    <div className="rounded-md border border-gray-200 bg-white p-3 text-xs text-gray-700 shadow-lg dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200">
      <p className="font-medium">{label ? formatDateLabel(label) : ''}</p>
      <p className="mt-1 text-kovalyx-goldText dark:text-kovalyx-gold">GMV: {formatGmv(row.total_gmv)}</p>
      <p className="text-gray-500 dark:text-gray-400">Orders: {row.total_orders}</p>
    </div>
  )
}

export function GmvAreaChart({ data }: GmvAreaChartProps) {
  const theme = useChartTheme()
  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="gmvGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#FFD700" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#FFD700" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
        <XAxis
          dataKey="period_date"
          tickFormatter={formatDateLabel}
          stroke={theme.axis}
          fontSize={12}
        />
        <YAxis tickFormatter={formatGmv} stroke={theme.axis} fontSize={12} />
        <Tooltip content={<GmvTooltip />} />
        <Area
          type="monotone"
          dataKey="total_gmv"
          stroke="#FFD700"
          strokeWidth={2}
          fill="url(#gmvGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
