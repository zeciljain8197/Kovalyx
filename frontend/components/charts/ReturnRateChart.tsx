'use client'

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { format } from 'date-fns'
import type { ReturnTrend } from '@/lib/queries/returns'

export interface ReturnRateChartProps {
  data: ReturnTrend[]
}

function formatPeriodLabel(dateStr: string): string {
  try {
    return format(new Date(dateStr), 'MMM yyyy')
  } catch {
    return dateStr
  }
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function ReturnRateTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: ReturnTrend }[]; label?: string }) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0].payload
  return (
    <div className="rounded-md border border-gray-800 bg-gray-900 p-3 text-xs text-gray-200 shadow-lg">
      <p className="font-medium">{label ? formatPeriodLabel(label) : ''}</p>
      <p className="mt-1 text-red-400">Return rate: {formatPct(row.return_rate)}</p>
      <p className="text-gray-400">Returned orders: {row.returned_orders}</p>
      <p className="text-gray-400">Total orders: {row.total_orders}</p>
    </div>
  )
}

export function ReturnRateChart({ data }: ReturnRateChartProps) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis dataKey="period_date" tickFormatter={formatPeriodLabel} stroke="#6b7280" fontSize={12} />
        <YAxis yAxisId="left" tickFormatter={formatPct} stroke="#6b7280" fontSize={12} />
        <YAxis yAxisId="right" orientation="right" stroke="#6b7280" fontSize={12} />
        <Tooltip content={<ReturnRateTooltip />} />
        <ReferenceLine
          yAxisId="left"
          y={0.05}
          stroke="#9ca3af"
          strokeDasharray="4 4"
          label={{ value: '5% threshold', position: 'insideTopRight', fill: '#9ca3af', fontSize: 11 }}
        />
        <Bar yAxisId="right" dataKey="returned_orders" fill="#f87171" fillOpacity={0.3} />
        <Line yAxisId="left" type="monotone" dataKey="return_rate" stroke="#ef4444" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
