import { getInventoryAlerts, getInventoryStats } from '@/lib/queries/inventory'
import { KpiCard } from '@/components/KpiCard'
import { InventoryStatusTable } from '@/components/charts/InventoryStatusTable'

export const revalidate = 120

export default async function InventoryPage() {
  const [alerts, stats] = await Promise.all([getInventoryAlerts(), getInventoryStats()])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Inventory Alerts</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard title="Total SKUs" value={stats.total_skus} />
        <KpiCard title="Red Alerts" value={stats.red_alerts} variant="danger" />
        <KpiCard title="Yellow Alerts" value={stats.yellow_alerts} variant="warning" />
        <KpiCard title="Healthy SKUs" value={stats.green_skus} variant="success" />
      </div>

      <p className="text-xs text-gray-500">
        Showing all SKUs. Red = below reorder point. Yellow = within 20% of reorder point.
      </p>

      <InventoryStatusTable data={alerts} />
    </div>
  )
}
