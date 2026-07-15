'use client'

// Small client-boundary wrapper, not one of the named deliverables.
// The Returns Analysis page asked for this bar chart "inline, not a
// separate component," but Recharts requires a Client Component and
// the page itself must stay a Server Component (it awaits data
// fetches directly) — a genuine inline JSX chart isn't possible under
// the App Router's Server/Client Component split, so this thin
// wrapper is the closest equivalent.
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ReturnsByCategory } from '@/lib/queries/returns'
import { useChartTheme } from '@/lib/chart-theme'

export interface ReturnsByCategoryChartProps {
  data: ReturnsByCategory[]
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function ReturnsByCategoryChart({ data }: ReturnsByCategoryChartProps) {
  const theme = useChartTheme()
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
        <XAxis dataKey="category" stroke={theme.axis} fontSize={12} />
        <YAxis tickFormatter={formatPct} stroke={theme.axis} fontSize={12} />
        <Tooltip
          formatter={(value: number) => formatPct(value)}
          contentStyle={{ background: theme.tooltipBg, border: `1px solid ${theme.tooltipBorder}`, fontSize: 12, color: theme.tooltipText }}
        />
        <Bar dataKey="return_rate" fill="#ef4444" fillOpacity={0.7} />
      </BarChart>
    </ResponsiveContainer>
  )
}
