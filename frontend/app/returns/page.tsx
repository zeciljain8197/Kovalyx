import { getReturnTrends, getReturnsByCategory, getTopReturnedProducts } from '@/lib/queries/returns'
import { KpiCard } from '@/components/KpiCard'
import { ReturnRateChart } from '@/components/charts/ReturnRateChart'
import { ReturnsByCategoryChart } from '@/components/charts/ReturnsByCategoryChart'
import { Table } from '@/components/ui/Table'
import { ArrowDown, ArrowUp, Minus } from 'lucide-react'

export const revalidate = 300

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function ChangeIndicator({ change }: { change: number | null }) {
  if (change === null || change === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-gray-500">
        <Minus size={12} /> 0.0%
      </span>
    )
  }
  const isUp = change > 0
  return (
    <span className={`inline-flex items-center gap-1 ${isUp ? 'text-red-400' : 'text-green-400'}`}>
      {isUp ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
      {formatPct(Math.abs(change))}
    </span>
  )
}

export default async function ReturnsPage() {
  const [trends, byCategory, topReturned] = await Promise.all([
    getReturnTrends(6),
    getReturnsByCategory(),
    getTopReturnedProducts(10),
  ])

  // mart_return_rates is monthly-grained; the most recent trend point is
  // the closest available proxy for "last 30 days" summary stats.
  const latest = trends[trends.length - 1]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Returns Analysis</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <KpiCard
          title="Overall Return Rate (latest month)"
          value={latest ? formatPct(latest.return_rate) : 'N/A'}
        />
        <KpiCard title="Total Returned Orders (latest month)" value={latest ? latest.returned_orders : 0} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-200">Return Rate Trend — Last 6 Months</h2>
        <ReturnRateChart data={trends} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-200">By Category</h2>
        <ReturnsByCategoryChart data={byCategory} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-200">Top Returned Products</h2>
        <Table
          headers={['Product', 'Category', 'Returned Orders', 'Return Rate', 'MoM Change']}
          rows={topReturned.map((p) => [
            p.product_name,
            p.category,
            String(p.returned_orders),
            formatPct(p.return_rate),
            <ChangeIndicator key={p.product_name} change={p.return_rate_change} />,
          ])}
          emptyMessage="No returns data available yet."
        />
      </div>
    </div>
  )
}
