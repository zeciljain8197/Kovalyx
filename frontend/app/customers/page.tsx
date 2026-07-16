import { getCohortData, getCustomerTierSummary } from '@/lib/queries/customers'
import { Card } from '@/components/ui/Card'
import { KpiCard } from '@/components/KpiCard'
import { CohortHeatmap } from '@/components/charts/CohortHeatmap'

export const revalidate = 300

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

const TIER_COLORS: Record<string, string> = {
  bronze: 'text-kovalyx-bronzeText dark:text-kovalyx-bronze border-l-kovalyx-bronze',
  silver: 'text-kovalyx-silverText dark:text-kovalyx-silver border-l-kovalyx-silver',
  gold: 'text-kovalyx-goldText dark:text-kovalyx-gold border-l-kovalyx-gold',
}

export default async function CustomersPage() {
  const [cohortData, tierSummary] = await Promise.all([getCohortData(), getCustomerTierSummary()])

  const tiers = [
    { key: 'bronze', label: 'Bronze Customers', count: tierSummary.bronze_count },
    { key: 'silver', label: 'Silver Customers', count: tierSummary.silver_count },
    { key: 'gold', label: 'Gold Customers', count: tierSummary.gold_count },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Customer Intelligence</h1>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {tiers.map((tier) => (
          <Card key={tier.key} className={`border-l-4 ${TIER_COLORS[tier.key]}`}>
            <p className="text-sm text-gray-500 dark:text-gray-400">{tier.label}</p>
            <p className={`mt-1 text-2xl font-bold ${TIER_COLORS[tier.key].split(' ').slice(0, 2).join(' ')}`}>{tier.count}</p>
            <p className="mt-1 text-xs text-gray-500">Ranked by lifetime spend tier</p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <KpiCard
          title="Total Customers"
          value={tierSummary.total_customers}
          subtitle="All registered customers, ordered or not"
        />
        <KpiCard
          title="Average Total Spent"
          value={formatCurrency(tierSummary.avg_total_spent)}
          subtitle="Lifetime spend per customer, across all orders"
        />
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-800 dark:text-gray-200">Cohort Retention</h2>
        <CohortHeatmap data={cohortData} />
        <p className="mt-3 text-xs text-gray-500 dark:text-gray-500">
          Cohort week = week of customer registration. Retention rate = % who placed an order in
          subsequent weeks.
        </p>
      </div>
    </div>
  )
}
