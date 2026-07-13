import { getDailySalesTrend, getHomeKpis, getSalesByCategory } from '@/lib/queries/sales'
import { KpiCard } from '@/components/KpiCard'
import { GmvAreaChart } from '@/components/charts/GmvAreaChart'
import { PipelineStatusBadge } from '@/components/PipelineStatusBadge'
import { Table } from '@/components/ui/Table'

export const revalidate = 300

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export default async function HomePage() {
  const [kpis, salesTrend, salesByCategory] = await Promise.all([
    getHomeKpis(),
    getDailySalesTrend(30),
    getSalesByCategory(),
  ])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Sales Overview</h1>
        <PipelineStatusBadge />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard title="Today's GMV" value={formatCurrency(kpis.todayGmv)} />
        <KpiCard title="Today's Orders" value={kpis.todayOrders} />
        <KpiCard title="Average Order Value" value={formatCurrency(kpis.todayAov)} />
        <KpiCard
          title="Active SKU Alerts"
          value={kpis.activeSkuAlerts}
          variant={kpis.activeSkuAlerts > 0 ? 'danger' : 'success'}
        />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-200">GMV — Last 30 Days</h2>
        <GmvAreaChart data={salesTrend} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-200">Top Categories</h2>
        <Table
          headers={['Category', 'GMV', 'Orders', 'Return Rate']}
          rows={salesByCategory.map((c) => [
            c.category,
            formatCurrency(c.total_gmv),
            String(c.total_orders),
            formatPct(c.return_rate),
          ])}
          emptyMessage="No sales data available yet."
        />
      </div>
    </div>
  )
}
