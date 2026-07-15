import { getDailySalesTrend, getHomeKpis, getSalesByCategory } from '@/lib/queries/sales'
import { KpiCard } from '@/components/KpiCard'
import { GmvAreaChart } from '@/components/charts/GmvAreaChart'
import { PipelineStatusBadge } from '@/components/PipelineStatusBadge'
import { Table } from '@/components/ui/Table'
import { HeroStrip } from '@/components/HeroStrip'
import { DateRangePicker } from '@/components/DateRangePicker'
import { parseRangeParam, rangeToDays, RANGE_PRESETS } from '@/lib/dateRange'

export const revalidate = 300

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: { range?: string }
}) {
  const range = parseRangeParam(searchParams.range)
  const days = rangeToDays(range)
  const rangeLabel = RANGE_PRESETS.find((p) => p.value === range)?.label ?? '30D'

  const [kpis, salesTrend, salesByCategory] = await Promise.all([
    getHomeKpis(),
    getDailySalesTrend(days),
    getSalesByCategory(days),
  ])

  return (
    <div className="space-y-6">
      <HeroStrip />

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Sales Overview</h1>
        <PipelineStatusBadge />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Today's GMV"
          value={formatCurrency(kpis.todayGmv)}
          subtitle="Gross merchandise value, most recent day the pipeline has data for"
        />
        <KpiCard title="Today's Orders" value={kpis.todayOrders} subtitle="Order count for the same day" />
        <KpiCard
          title="Average Order Value"
          value={formatCurrency(kpis.todayAov)}
          subtitle="Today's GMV ÷ today's orders"
        />
        <KpiCard
          title="Active SKU Alerts"
          value={kpis.activeSkuAlerts}
          subtitle="SKUs currently below or near their reorder threshold"
          variant={kpis.activeSkuAlerts > 0 ? 'danger' : 'success'}
        />
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">GMV — {rangeLabel}</h2>
          <DateRangePicker />
        </div>
        <GmvAreaChart data={salesTrend} />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-800 dark:text-gray-200">Top Categories ({rangeLabel})</h2>
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
